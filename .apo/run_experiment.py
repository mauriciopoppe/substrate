#!/usr/bin/env python3
"""APO Benchmark Execution Harness for Substrate E2E TTFI Study.

Conforms to the APO Benchmark Execution Contract:
1. Accepts --results-dir (positional or flag), --iterations/-n (default: 3).
2. Writes PID to <RESULTS_DIR>/monitor/benchmark.pid.
3. Streams execution logs to <RESULTS_DIR>/benchmark_output.log.
4. Reconciles cluster state, cleans stale Postgres actor state, and runs Boomer.
5. Slices stats into <RESULTS_DIR>/summary.json (on success) or <RESULTS_DIR>/error.json (on failure).
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple


def run_cmd(
    cmd: List[str] | str,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    shell: bool = False,
    stdout: Optional[int] = None,
    stderr: Optional[int] = None,
) -> subprocess.CompletedProcess:
  """Runs a shell or exec command."""
  return subprocess.run(
      cmd,
      cwd=cwd,
      env=env,
      check=check,
      shell=shell,
      stdout=stdout,
      stderr=stderr,
      text=True,
  )


def source_env_file(filepath: str, env: Dict[str, str]) -> Dict[str, str]:
  """Sources a bash file and returns updated environment variables."""
  if not os.path.exists(filepath):
    return env
  cmd = f"source '{filepath}' 2>/dev/null && env -0"
  res = subprocess.run(["bash", "-c", cmd], env=env, stdout=subprocess.PIPE, text=False)
  if res.returncode == 0:
    for entry in res.stdout.split(b"\x00"):
      if not entry:
        continue
      parts = entry.decode("utf-8", errors="replace").split("=", 1)
      if len(parts) == 2:
        env[parts[0]] = parts[1]
  return env


def parse_iteration_stats(iter_dir: str, test_name: str) -> Dict[str, Any]:
  """Parses CSV metrics, dmesg OOMs, and pprof hotspots for a single iteration."""
  stats_files = glob.glob(os.path.join(iter_dir, "*stats.csv"))
  if not stats_files:
    stats_files = glob.glob(os.path.join(iter_dir, f"{test_name}_stats.csv"))

  metrics: Dict[str, float] = {
      "ttfi_p90_ms": 0.0,
      "ttfi_p95_ms": 0.0,
      "suspend_actor_p95_ms": 0.0,
  }
  constraints: Dict[str, Any] = {
      "error_rate": 0.0,
      "node_oom_events": 0,
      "client_send_rate_ratio": 1.0,
  }
  raw_stats: List[Dict[str, str]] = []

  total_requests = 0
  total_failures = 0

  if stats_files and os.path.exists(stats_files[0]):
    with open(stats_files[0], "r", encoding="utf-8") as f:
      reader = csv.DictReader(f)
      for row in reader:
        raw_stats.append(row)
        name = row.get("Name", "")

        try:
          req_cnt = int(row.get("Request Count", 0))
          fail_cnt = int(row.get("Failure Count", 0))
          if name != "Aggregated":
            total_requests += req_cnt
            total_failures += fail_cnt
        except (ValueError, TypeError):
          pass

        p90_val = 0.0
        for col in ("90%", "p90"):
          if col in row and row[col]:
            try:
              p90_val = float(row[col])
            except ValueError:
              pass

        p95_val = 0.0
        for col in ("95%", "p95"):
          if col in row and row[col]:
            try:
              p95_val = float(row[col])
            except ValueError:
              pass

        if name == "GluttonReadRAM":
          metrics["ttfi_p90_ms"] = p90_val
          metrics["ttfi_p95_ms"] = p95_val
        elif name == "SuspendActor":
          metrics["suspend_actor_p95_ms"] = p95_val

    if total_requests > 0:
      constraints["error_rate"] = float(total_failures) / float(total_requests)
  else:
    print(f"Warning: No stats CSV found in {iter_dir}")

  # Check for OOM events
  oom_events = 0
  dmesg_file = os.path.join(iter_dir, "dmesg.txt")
  if os.path.exists(dmesg_file):
    with open(dmesg_file, "r", encoding="utf-8") as f:
      content = f.read()
      oom_events = content.lower().count("oom-killer") + content.lower().count("out of memory")
  constraints["node_oom_events"] = oom_events

  # Extract CPU hotspots if present
  cpu_top_file = os.path.join(iter_dir, "profiles", "cpu_top.txt")
  cpu_hotspots: List[Dict[str, str]] = []
  if os.path.exists(cpu_top_file):
    with open(cpu_top_file, "r", encoding="utf-8") as f:
      lines = f.readlines()
    for line in lines[8:20]:
      parts = line.strip().split()
      if len(parts) >= 6:
        cpu_hotspots.append({
            "flat": parts[0],
            "flat_pct": parts[1],
            "cum": parts[3],
            "cum_pct": parts[4],
            "symbol": " ".join(parts[5:]),
        })

  summary: Dict[str, Any] = {
      "status": "COMPLETED",
      "metrics": metrics,
      "constraints": constraints,
      "profiling_summary": {
          "cpu_hotspots": cpu_hotspots,
          "cpu_profile_path": os.path.join(iter_dir, "profiles", "cpu.pb.gz"),
          "heap_profile_path": os.path.join(iter_dir, "profiles", "heap.pb.gz"),
      },
      "raw_stats": raw_stats,
  }

  summary_path = os.path.join(iter_dir, "summary.json")
  with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)
  print(f"Successfully generated {summary_path} with TTFI metrics:", metrics)
  return summary


def aggregate_iterations(results_dir: str, iterations: int) -> Dict[str, Any]:
  """Consolidates and aggregates results across iterations using the median trial."""
  iter_summaries: List[Tuple[int, Dict[str, Any]]] = []
  for i in range(1, iterations + 1):
    iter_file = os.path.join(results_dir, f"iter_{i}", "summary.json")
    if os.path.exists(iter_file):
      try:
        with open(iter_file, "r", encoding="utf-8") as f:
          data = json.load(f)
          if data.get("metrics", {}).get("ttfi_p90_ms", 0.0) > 0:
            iter_summaries.append((i, data))
          else:
            print(f"Warning: {iter_file} contains zeroed metrics: {data.get('metrics')}")
      except Exception as e:
        print(f"Warning: Could not read {iter_file}: {e}")

  if not iter_summaries:
    error_payload = {
        "error": "No valid iteration summaries found",
        "stage": "aggregation",
    }
    with open(os.path.join(results_dir, "error.json"), "w", encoding="utf-8") as f:
      json.dump(error_payload, f, indent=2)
    raise RuntimeError("No valid iteration summaries found to aggregate.")

  # Sort iterations by primary objective (ttfi_p90_ms ascending)
  iter_summaries.sort(key=lambda item: item[1].get("metrics", {}).get("ttfi_p90_ms", float("inf")))
  median_idx, median_summary = iter_summaries[len(iter_summaries) // 2]
  print(f"Selected median iteration: iter_{median_idx}")

  # Copy artifacts from the median iteration to top-level results_dir
  median_iter_dir = os.path.join(results_dir, f"iter_{median_idx}")
  artifacts_to_copy = [
      "stats.csv",
      "stats_history.csv",
      "failures.csv",
      "exceptions.csv",
      "logs.txt",
      "traces.txt",
      "status.json",
      "stats.jsonl",
  ]
  for fname in artifacts_to_copy:
    src = os.path.join(median_iter_dir, fname)
    dst = os.path.join(results_dir, fname)
    if os.path.exists(src):
      shutil.copy2(src, dst)

  median_profiles_dir = os.path.join(median_iter_dir, "profiles")
  dst_profiles_dir = os.path.join(results_dir, "profiles")
  if os.path.exists(median_profiles_dir):
    for pf in os.listdir(median_profiles_dir):
      shutil.copy2(os.path.join(median_profiles_dir, pf), os.path.join(dst_profiles_dir, pf))

  top_summary: Dict[str, Any] = {
      "status": "COMPLETED",
      "iterations": iterations,
      "median_iteration_index": median_idx,
      "metrics": median_summary.get("metrics", {}),
      "constraints": median_summary.get("constraints", {}),
      "profiling_summary": median_summary.get("profiling_summary", {}),
      "raw_stats": median_summary.get("raw_stats", []),
      "iteration_breakdown": [
          {
              "iteration": idx,
              "metrics": s.get("metrics", {}),
              "constraints": s.get("constraints", {}),
          }
          for idx, s in iter_summaries
      ],
  }

  target_summary_path = os.path.join(results_dir, "summary.json")
  with open(target_summary_path, "w", encoding="utf-8") as f:
    json.dump(top_summary, f, indent=2)

  print(f"Generated aggregated {target_summary_path} successfully (median iteration: {median_idx}).")
  print(json.dumps(top_summary["metrics"], indent=2))
  return top_summary


def cleanup_stale_cluster_state(env: Dict[str, str]) -> None:
  """Purges leftover jobs/pods, clears DB actor records, and restarts ateom."""
  print("Ensuring cluster is clean from previous benchmark runs (idempotency check)...")
  subprocess.run(
      ["kubectl", "delete", "jobs,pods", "-n", "benchmarking", "--all", "--wait=false"],
      env=env,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
  )

  sql_purge = (
      "DELETE FROM worker_assignments WHERE actor_uid IN (SELECT uid FROM actors WHERE atespace='benchmark');"
      "DELETE FROM actor_egress_policies WHERE atespace='benchmark';"
      "DELETE FROM actors WHERE atespace='benchmark';"
  )
  subprocess.run(
      [
          "kubectl",
          "exec",
          "-n",
          "ate-system",
          "pod/postgres-0",
          "-c",
          "postgres",
          "--",
          "psql",
          "-U",
          "postgres",
          "-d",
          "atepg",
          "-q",
          "-c",
          sql_purge,
      ],
      env=env,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
  )

  print("Resetting benchmark-ateom worker pool...")
  subprocess.run(
      ["kubectl", "rollout", "restart", "deployment/benchmark-ateom", "-n", "benchmark-workloads"],
      env=env,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
  )
  subprocess.run(
      ["kubectl", "rollout", "status", "deployment/benchmark-ateom", "-n", "benchmark-workloads", "--timeout=120s"],
      env=env,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
  )


def flush_node_page_caches(env: Dict[str, str]) -> None:
  """Runs a privileged job on the benchmark node to drop host caches."""
  print("Flushing node page caches and syncing block devices on benchmark node...")
  flush_job_yaml = """apiVersion: batch/v1
kind: Job
metadata:
  name: node-cache-flush
  namespace: benchmarking
spec:
  ttlSecondsAfterFinished: 10
  template:
    spec:
      restartPolicy: Never
      hostPID: true
      nodeSelector:
        ate.dev/substrate-version: substrate-local
      tolerations:
      - operator: Exists
      containers:
      - name: flush
        image: debian:stable-slim
        securityContext:
          privileged: true
        command:
        - "sh"
        - "-c"
        - "sync && echo 3 > /proc/sys/vm/drop_caches"
"""
  proc = subprocess.run(
      ["kubectl", "apply", "-f", "-"],
      input=flush_job_yaml,
      text=True,
      env=env,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
  )
  if proc.returncode == 0:
    subprocess.run(
        ["kubectl", "wait", "--for=condition=complete", "job/node-cache-flush", "-n", "benchmarking", "--timeout=30s"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
  subprocess.run(
      ["kubectl", "delete", "job/node-cache-flush", "-n", "benchmarking", "--wait=false"],
      env=env,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
      check=False,
  )


def build_runner_job_yaml(
    job_name: str,
    run_tag: str,
    test_name: str,
    test_file: str,
    duration: str,
    users: str,
    dest: str,
    trace_prob: str,
    mem_target: str,
    mem_churn: str,
    mem_read: str,
    resume_mode: str,
    runner_image: str,
) -> str:
  """Constructs the Kubernetes Job manifest for the boomer benchmark runner."""
  return f"""apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: automated-benchmarking-permissions
  namespace: ate-system
subjects:
- kind: ServiceAccount
  name: benchmark-runner
  namespace: benchmarking
roleRef:
  kind: Role
  name: atelet-endpointslices
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: batch/v1
kind: Job
metadata:
  name: {job_name}
  namespace: benchmarking
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels:
        app: substrate-benchmark-runner
        test-name: {test_name}
        tag: {run_tag}
    spec:
      restartPolicy: Never
      serviceAccountName: benchmark-runner
      containers:
      - name: runner
        image: {runner_image}
        imagePullPolicy: IfNotPresent
        command:
        - "python3"
        - "/app/runner.py"
        args:
        - "-f"
        - "{test_file}"
        - "-t"
        - "{duration}"
        - "-u"
        - "{users}"
        - "--tag"
        - "{run_tag}"
        - "--name"
        - "{test_name}"
        - "--dest"
        - "{dest}"
        - "--trace-probability"
        - "{trace_prob}"
        - "--mem-target"
        - "{mem_target}"
        - "--mem-churn"
        - "{mem_churn}"
        - "--mem-read"
        - "{mem_read}"
        - "--resume-mode"
        - "{resume_mode}"
        env:
        - name: OTEL_EXPORTER_OTLP_ENDPOINT
          value: http://opentelemetry-collector.gke-managed-otel.svc.cluster.local:4317
        volumeMounts:
        - name: servicedns-ca
          mountPath: /run/servicedns-ca
          readOnly: true
        - name: podidentity
          mountPath: /run/podidentity.podcert.ate.dev
          readOnly: true
        resources:
          requests:
            cpu: "1"
            memory: "1Gi"
      volumes:
      - name: servicedns-ca
        projected:
          sources:
          - clusterTrustBundle:
              signerName: servicedns.podcert.ate.dev/identity
              labelSelector:
                matchLabels:
                  podcert.ate.dev/canarying: live
              path: ca.crt
      - name: podidentity
        projected:
          sources:
          - podCertificate:
              signerName: podidentity.podcert.ate.dev/identity
              keyType: ECDSAP256
              credentialBundlePath: credential-bundle.pem
"""


def main() -> None:
  parser = argparse.ArgumentParser(description="Substrate E2E TTFI Benchmark Harness")
  parser.add_argument("positional_results_dir", nargs="?", default="", help="Results output directory")
  parser.add_argument("--results-dir", default="", help="Results output directory")
  parser.add_argument("-n", "--iterations", type=int, default=int(os.environ.get("BENCHMARK_ITERATIONS", 3)), help="Iterations")
  args = parser.parse_args()

  results_dir = args.results_dir or args.positional_results_dir or "results/scratch"
  results_dir = os.path.abspath(results_dir)
  iterations = args.iterations

  apo_dir = os.path.dirname(os.path.abspath(__file__))
  workspace_dir = os.path.abspath(os.path.join(apo_dir, ".."))
  os.chdir(workspace_dir)

  os.makedirs(os.path.join(results_dir, "monitor"), exist_ok=True)
  os.makedirs(os.path.join(results_dir, "profiles"), exist_ok=True)

  # Write benchmark PID
  with open(os.path.join(results_dir, "monitor", "benchmark.pid"), "w", encoding="utf-8") as f:
    f.write(f"{os.getpid()}\n")

  # Setup execution environment
  env = dict(os.environ)
  env = source_env_file(os.path.join(apo_dir, "set-env.sh"), env)
  env = source_env_file(os.path.join(apo_dir, "manifests", "tunables.env"), env)
  env = source_env_file(os.path.join(results_dir, "build_artifacts.env"), env)

  print(f"Starting Substrate E2E TTFI Benchmark execution in {workspace_dir} ({iterations} iterations)...")

  # Step 0: Ensure idempotency
  cleanup_stale_cluster_state(env)

  # Step 1: Deploy built custom images if present
  atelet_image = env.get("ATELET_IMAGE")
  if atelet_image:
    print(f"Deploying custom atelet image: {atelet_image}")
    subprocess.run(
        ["kubectl", "set", "image", "daemonset/atelet-substrate-local", "-n", "ate-system", f"atelet={atelet_image}"],
        env=env,
        check=False,
    )
    subprocess.run(
        ["kubectl", "rollout", "status", "daemonset/atelet-substrate-local", "-n", "ate-system", "--timeout=120s"],
        env=env,
        check=False,
    )

  # Step 2: Reconcile WorkerPool and ActorTemplate
  sandbox_class = env.get("SANDBOX_CLASS", "gvisor")
  worker_count = env.get("WORKER_COUNT", "1")
  actor_memory = env.get("ACTOR_MEMORY", "1536Mi")

  print(f"Reconciling benchmark worker pool and glutton ActorTemplate (sandbox-class={sandbox_class})...")
  deploy_cmd = [
      "./benchmarking/workloads/deploy.sh",
      "--deploy",
      f"--worker-count={worker_count}",
      f"--sandbox-class={sandbox_class}",
      f"--actor-memory={actor_memory}",
  ]
  deploy_env = dict(env)
  deploy_env["WORKLOAD_TEMPLATES"] = "glutton"
  subprocess.run(deploy_cmd, env=deploy_env, cwd=workspace_dir, check=True)

  ateom_microvm_image = env.get("ATEOM_MICROVM_IMAGE")
  if ateom_microvm_image and sandbox_class == "microvm":
    print(f"Deploying custom ateom-microvm image: {ateom_microvm_image}")
    subprocess.run(
        ["kubectl", "set", "image", "deployment/benchmark-ateom", "-n", "benchmark-workloads", f"ateom={ateom_microvm_image}"],
        env=env,
        check=False,
    )
    subprocess.run(
        ["kubectl", "rollout", "status", "deployment/benchmark-ateom", "-n", "benchmark-workloads", "--timeout=120s"],
        env=env,
        check=False,
    )

  # Step 3: Setup runner namespace and service account
  project_id = env.get("PROJECT_ID", "mauriciopoppe-gke-dev")
  subprocess.run(["kubectl", "create", "namespace", "benchmarking", "--dry-run=client", "-o", "yaml"], stdout=subprocess.PIPE, env=env, check=True)
  subprocess.run(["kubectl", "apply", "-f", "-"], input="apiVersion: v1\nkind: Namespace\nmetadata:\n  name: benchmarking\n", text=True, env=env, check=True)

  sa_yaml = f"""apiVersion: v1
kind: ServiceAccount
metadata:
  name: benchmark-runner
  namespace: benchmarking
  annotations:
    iam.gke.io/gcp-service-account: "mauriciopoppe-gke-dev-sa@{project_id}.iam.gserviceaccount.com"
"""
  subprocess.run(["kubectl", "apply", "-f", "-"], input=sa_yaml, text=True, env=env, check=True)

  # Base runner parameters
  test_name = env.get("TEST_NAME", "glutton_mem_512mi_gvisor_implicit")
  test_file = env.get("TEST_FILE", "/app/tests/glutton.py")
  duration = env.get("DURATION", env.get("BENCHMARK_DURATION", "2m"))
  users = env.get("USERS", env.get("BENCHMARK_USERS", "1"))
  trace_prob = env.get("TRACE_PROBABILITY", "1.0")
  bucket_name = env.get("BUCKET_NAME", f"ate-snapshots-{project_id}-us-west1-c")
  dest = f"gs://{bucket_name}/benchmarks"
  runner_image = f"us-docker.pkg.dev/{project_id}/gcr.io/ate-images/locust-test:latest"

  mem_target = env.get("BENCHMARK_MEM_TARGET", "512Mi")
  mem_churn = env.get("BENCHMARK_MEM_CHURN", "64Mi")
  mem_read = env.get("BENCHMARK_MEM_READ", "64Mi")
  resume_mode = env.get("BENCHMARK_RESUME_MODE", "implicit")

  top_log_file = os.path.join(results_dir, "benchmark_output.log")

  print(f"=== Executing {iterations} Benchmark Iteration(s) ===")

  for iter_num in range(1, iterations + 1):
    print("==========================================================")
    print(f"=== [Iteration {iter_num} / {iterations}] ===")
    print("==========================================================")

    iter_dir = os.path.join(results_dir, f"iter_{iter_num}")
    os.makedirs(os.path.join(iter_dir, "monitor"), exist_ok=True)
    os.makedirs(os.path.join(iter_dir, "profiles"), exist_ok=True)

    # Clean previous run resources
    subprocess.run(
        ["kubectl", "delete", "jobs,pods", "-n", "benchmarking", "--all", "--wait=false"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )

    # Reset Postgres actors & ateom pool
    print("Purging leftover benchmark actors from database...")
    cleanup_stale_cluster_state(env)

    # Flush node page caches
    flush_node_page_caches(env)

    # Submit runner Job
    iter_ts = int(time.time())
    run_tag = f"run-{iter_ts}-iter-{iter_num}"
    job_name = f"runner-glutton-{iter_ts}-{iter_num}"

    job_yaml = build_runner_job_yaml(
        job_name=job_name,
        run_tag=run_tag,
        test_name=test_name,
        test_file=test_file,
        duration=duration,
        users=users,
        dest=dest,
        trace_prob=trace_prob,
        mem_target=mem_target,
        mem_churn=mem_churn,
        mem_read=mem_read,
        resume_mode=resume_mode,
        runner_image=runner_image,
    )

    print(f"Submitting benchmark runner Job {job_name} for Iteration {iter_num}...")
    subprocess.run(["kubectl", "apply", "-f", "-"], input=job_yaml, text=True, env=env, check=True)

    # Wait for Job to complete
    print(f"Waiting for benchmark runner Job {job_name} to complete...")
    job_timeout_secs = 600
    wait_cmd = [
        "kubectl",
        "wait",
        "--for=condition=complete",
        f"job/{job_name}",
        "-n",
        "benchmarking",
        f"--timeout={job_timeout_secs}s",
    ]
    wait_res = subprocess.run(wait_cmd, env=env, check=False)

    if wait_res.returncode != 0:
      print(f"Job {job_name} did not complete within {job_timeout_secs}s. Checking for failure...")
      subprocess.run(["kubectl", "get", "job", job_name, "-n", "benchmarking", "-o", "yaml"], env=env, check=False)
      subprocess.run(["kubectl", "logs", f"job/{job_name}", "-n", "benchmarking", "--tail=200"], env=env, check=False)
      with open(os.path.join(iter_dir, "error.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "status": "FAILED",
                "stage": "benchmark_execution",
                "iteration": iter_num,
                "error": f"Job {job_name} timed out or failed",
            },
            f,
            indent=2,
        )
      continue

    # Stream Job logs
    iter_log_path = os.path.join(iter_dir, "benchmark_output.log")
    with open(iter_log_path, "w", encoding="utf-8") as log_f:
      subprocess.run(["kubectl", "logs", f"job/{job_name}", "-n", "benchmarking"], stdout=log_f, env=env, check=False)

    with open(iter_log_path, "r", encoding="utf-8") as log_f, open(top_log_file, "a", encoding="utf-8") as top_f:
      shutil.copyfileobj(log_f, top_f)

    subprocess.run(["kubectl", "delete", "job", job_name, "-n", "benchmarking"], env=env, check=False)

    # Download stats from GCS
    print(f"Downloading benchmark results from GCS for Iteration {iter_num} ({run_tag})...")
    gcs_run_dir = ""
    gcs_ls = subprocess.run(
        ["gcloud", "storage", "ls", "--recursive", f"{dest}/runs/{test_name}/**/*{run_tag}/stats.csv"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if gcs_ls.returncode == 0 and gcs_ls.stdout.strip():
      first_line = gcs_ls.stdout.strip().splitlines()[0]
      gcs_run_dir = first_line.rsplit("/stats.csv", 1)[0]

    if gcs_run_dir:
      print(f"Found GCS run directory: {gcs_run_dir}")
      subprocess.run(["gcloud", "storage", "cp", "-r", f"{gcs_run_dir}/*", f"{iter_dir}/"], env=env, check=False)
    else:
      print(f"Fallback searching for any run files matching {run_tag}...")
      fallback_src = f"{dest}/runs/{test_name}/*/*/*{run_tag}/*"
      subprocess.run(f"gcloud storage cp -r {fallback_src} '{iter_dir}/'", shell=True, env=env, check=False)

    # Parse iteration metrics
    try:
      parse_iteration_stats(iter_dir, test_name)
    except Exception as e:
      print(f"Error processing iteration {iter_num} results: {e}")
      with open(os.path.join(iter_dir, "error.json"), "w", encoding="utf-8") as f:
        json.dump({"error": str(e), "stage": "iter_post_processing"}, f, indent=2)

  print(f"=== Consolidating & Aggregating Metrics across {iterations} Iteration(s) ===")
  aggregate_iterations(results_dir, iterations)


if __name__ == "__main__":
  main()
