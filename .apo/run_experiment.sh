#!/bin/bash
# ==============================================================================
# Benchmark Execution Script for Substrate E2E TTFI Study
# Conforms to the APO Benchmark Execution Contract:
# 1. Accepts $1 as <RESULTS_DIR>, supports --iterations / -n (default: 3)
# 2. Writes shell PID $! to <RESULTS_DIR>/monitor/benchmark.pid
# 3. Streams stdout/stderr to <RESULTS_DIR>/benchmark_output.log
# 4. Deploys custom atelet/ateom images if built by build.sh
# 5. Writes clean metrics to <RESULTS_DIR>/summary.json or diagnostic errors to <RESULTS_DIR>/error.json
# ==============================================================================

set -euo pipefail

RESULTS_DIR=""
BENCHMARK_ITERATIONS="${BENCHMARK_ITERATIONS:-3}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --iterations|-n)
      BENCHMARK_ITERATIONS="$2"
      shift 2
      ;;
    *)
      if [ -z "$RESULTS_DIR" ]; then
        RESULTS_DIR="$1"
      fi
      shift
      ;;
  esac
done

RESULTS_DIR="${RESULTS_DIR:-results/scratch}"
mkdir -p "${RESULTS_DIR}/monitor" "${RESULTS_DIR}/profiles"
echo $$ > "${RESULTS_DIR}/monitor/benchmark.pid"

APO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
WORKSPACE_DIR="$(cd "${APO_DIR}/.." &> /dev/null && pwd)"
cd "${WORKSPACE_DIR}"

# Source runtime environment if available
if [ -f "${APO_DIR}/set-env.sh" ]; then
  # shellcheck disable=SC1091
  source "${APO_DIR}/set-env.sh"
fi

# Source tunables if available
if [ -f "${APO_DIR}/manifests/tunables.env" ]; then
  # shellcheck disable=SC1091
  source "${APO_DIR}/manifests/tunables.env"
fi

echo "Starting Substrate E2E TTFI Benchmark execution in ${WORKSPACE_DIR} (${BENCHMARK_ITERATIONS} iterations)..."

# Step 0: Ensure idempotency by cleaning up stale resources from previous benchmark runs
echo "Ensuring cluster is clean from previous benchmark runs (idempotency check)..."
kubectl delete jobs,pods -n benchmarking --all --wait=false 2>/dev/null || true

kubectl exec -n ate-system pod/postgres-0 -c postgres -- \
  psql -U postgres -d atepg -q -c "
    DELETE FROM worker_assignments WHERE actor_uid IN (SELECT uid FROM actors WHERE atespace='benchmark');
    DELETE FROM actor_egress_policies WHERE atespace='benchmark';
    DELETE FROM actors WHERE atespace='benchmark';
  " 2>/dev/null || true

echo "Resetting benchmark-ateom worker pool..."
kubectl rollout restart deployment/benchmark-ateom -n benchmark-workloads >/dev/null 2>&1 || true
kubectl rollout status deployment/benchmark-ateom -n benchmark-workloads --timeout=120s >/dev/null 2>&1 || true

# Step 1: Deploy built container images if present
if [ -f "${RESULTS_DIR}/build_artifacts.env" ]; then
  # shellcheck disable=SC1091
  source "${RESULTS_DIR}/build_artifacts.env"
fi

if [ -n "${ATELET_IMAGE:-}" ]; then
  echo "Deploying custom atelet image: ${ATELET_IMAGE}"
  kubectl set image daemonset/atelet-substrate-local -n ate-system atelet="${ATELET_IMAGE}"
  kubectl rollout status daemonset/atelet-substrate-local -n ate-system --timeout=120s || true
fi

# Step 2: Ensure benchmark workloads (WorkerPool and ActorTemplate) are ready
SANDBOX_CLASS="${SANDBOX_CLASS:-gvisor}"
WORKER_COUNT="${WORKER_COUNT:-1}"
ACTOR_MEMORY="${ACTOR_MEMORY:-1536Mi}"

echo "Reconciling benchmark worker pool and glutton ActorTemplate (sandbox-class=${SANDBOX_CLASS})..."
WORKLOAD_TEMPLATES="glutton" ./benchmarking/workloads/deploy.sh \
  --deploy \
  --worker-count="${WORKER_COUNT}" \
  --sandbox-class="${SANDBOX_CLASS}" \
  --actor-memory="${ACTOR_MEMORY}"

if [ -n "${ATEOM_MICROVM_IMAGE:-}" ] && [ "${SANDBOX_CLASS}" == "microvm" ]; then
  echo "Deploying custom ateom-microvm image: ${ATEOM_MICROVM_IMAGE}"
  kubectl set image deployment/benchmark-ateom -n benchmark-workloads ateom="${ATEOM_MICROVM_IMAGE}"
  kubectl rollout status deployment/benchmark-ateom -n benchmark-workloads --timeout=120s || true
fi

# Step 3: Setup runner namespace and service account with Workload Identity
kubectl create namespace benchmarking --dry-run=client -o yaml | kubectl apply -f -
kubectl create serviceaccount benchmark-runner -n benchmarking --dry-run=client -o yaml | kubectl apply -f -
kubectl annotate serviceaccount benchmark-runner -n benchmarking \
  iam.gke.io/gcp-service-account="mauriciopoppe-gke-dev-sa@${PROJECT_ID}.iam.gserviceaccount.com" --overwrite

# Base benchmark runner parameters
TEST_NAME="${TEST_NAME:-glutton_mem_512mi_gvisor_implicit}"
TEST_FILE="${TEST_FILE:-/app/tests/glutton.py}"
DURATION="${DURATION:-${BENCHMARK_DURATION:-2m}}"
USERS="${USERS:-${BENCHMARK_USERS:-1}}"
TRACE_PROBABILITY="${TRACE_PROBABILITY:-1.0}"
RUNNER_IMAGE="us-docker.pkg.dev/${PROJECT_ID}/gcr.io/ate-images/locust-test:latest"
DEST="gs://${BUCKET_NAME}/benchmarks"

echo "=== Executing ${BENCHMARK_ITERATIONS} Benchmark Iteration(s) ==="

for iter in $(seq 1 "${BENCHMARK_ITERATIONS}"); do
  echo "=========================================================="
  echo "=== [Iteration ${iter} / ${BENCHMARK_ITERATIONS}] ==="
  echo "=========================================================="

  ITER_DIR="${RESULTS_DIR}/iter_${iter}"
  mkdir -p "${ITER_DIR}/monitor" "${ITER_DIR}/profiles"

  # Clean up leftover runner jobs or pods
  kubectl delete jobs,pods -n benchmarking --all --wait=false 2>/dev/null || true

  # Purge leftover benchmark actors from Substrate database
  echo "Purging leftover benchmark actors from database..."
  kubectl exec -n ate-system pod/postgres-0 -c postgres -- \
    psql -U postgres -d atepg -q -c "
      DELETE FROM worker_assignments WHERE actor_uid IN (SELECT uid FROM actors WHERE atespace='benchmark');
      DELETE FROM actor_egress_policies WHERE atespace='benchmark';
      DELETE FROM actors WHERE atespace='benchmark';
    " 2>/dev/null || true

  # Reset benchmark worker pool
  echo "Resetting benchmark worker pool for iteration ${iter}..."
  kubectl rollout restart deployment/benchmark-ateom -n benchmark-workloads >/dev/null 2>&1 || true
  kubectl rollout status deployment/benchmark-ateom -n benchmark-workloads --timeout=120s >/dev/null 2>&1 || true

  # Flush dirty writeback buffers and drop kernel page caches on benchmark node
  echo "Flushing node page caches and syncing block devices on benchmark node..."
  kubectl apply -f - << 'EOF' 2>/dev/null || true
apiVersion: batch/v1
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
EOF
  kubectl wait --for=condition=complete job/node-cache-flush -n benchmarking --timeout=30s 2>/dev/null || true
  kubectl delete job/node-cache-flush -n benchmarking --wait=false 2>/dev/null || true

  # Construct and submit the benchmark runner Job
  ITER_TS="$(date +%s)"
  RUN_TAG="run-${ITER_TS}-iter-${iter}"
  JOB_NAME="runner-glutton-${ITER_TS}-${iter}"

  JOB_MANIFEST="$(mktemp --suffix=.yaml)"
  cat <<EOF > "${JOB_MANIFEST}"
apiVersion: rbac.authorization.k8s.io/v1
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
  name: ${JOB_NAME}
  namespace: benchmarking
spec:
  backoffLimit: 0
  ttlSecondsAfterFinished: 86400
  template:
    metadata:
      labels:
        app: substrate-benchmark-runner
        test-name: ${TEST_NAME}
        tag: ${RUN_TAG}
    spec:
      restartPolicy: Never
      serviceAccountName: benchmark-runner
      containers:
      - name: runner
        image: ${RUNNER_IMAGE}
        imagePullPolicy: IfNotPresent
        command:
        - "python3"
        - "/app/runner.py"
        args:
        - "-f"
        - "${TEST_FILE}"
        - "-t"
        - "${DURATION}"
        - "-u"
        - "${USERS}"
        - "--tag"
        - "${RUN_TAG}"
        - "--name"
        - "${TEST_NAME}"
        - "--dest"
        - "${DEST}"
        - "--trace-probability"
        - "${TRACE_PROBABILITY}"
        - "--mem-target"
        - "${BENCHMARK_MEM_TARGET:-512Mi}"
        - "--mem-churn"
        - "${BENCHMARK_MEM_CHURN:-64Mi}"
        - "--mem-read"
        - "${BENCHMARK_MEM_READ:-64Mi}"
        - "--resume-mode"
        - "${BENCHMARK_RESUME_MODE:-implicit}"
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
EOF

  echo "Submitting benchmark runner Job ${JOB_NAME} for Iteration ${iter}..."
  kubectl apply -f "${JOB_MANIFEST}"
  rm -f "${JOB_MANIFEST}"

  # Wait for Job to complete
  echo "Waiting for benchmark runner Job ${JOB_NAME} to complete..."
  JOB_TIMEOUT_SECS=600

  if ! kubectl wait --for=condition=complete "job/${JOB_NAME}" -n benchmarking --timeout="${JOB_TIMEOUT_SECS}s"; then
    echo "Job ${JOB_NAME} did not complete within ${JOB_TIMEOUT_SECS}s. Checking for failure..."
    kubectl get job "${JOB_NAME}" -n benchmarking -o yaml || true
    kubectl logs "job/${JOB_NAME}" -n benchmarking --tail=200 || true
    cat <<EOF > "${ITER_DIR}/error.json"
{
  "status": "FAILED",
  "stage": "benchmark_execution",
  "iteration": ${iter},
  "error": "Job ${JOB_NAME} timed out or failed"
}
EOF
    continue
  fi

  # Stream Job logs into ITER_DIR and append to top-level log
  kubectl logs "job/${JOB_NAME}" -n benchmarking > "${ITER_DIR}/benchmark_output.log" 2>&1 || true
  cat "${ITER_DIR}/benchmark_output.log" >> "${RESULTS_DIR}/benchmark_output.log" 2>&1 || true
  kubectl delete job "${JOB_NAME}" -n benchmarking 2>/dev/null || true

  # Download stats and traces from GCS
  echo "Downloading benchmark results from GCS for Iteration ${iter} (${RUN_TAG})..."
  GCS_RUN_DIR=$(gcloud storage ls --recursive "${DEST}/runs/${TEST_NAME}/**/*${RUN_TAG}/stats.csv" 2>/dev/null | head -n 1 | sed 's|/stats.csv$||' || true)
  if [ -n "${GCS_RUN_DIR}" ]; then
    echo "Found GCS run directory: ${GCS_RUN_DIR}"
    gcloud storage cp -r "${GCS_RUN_DIR}/*" "${ITER_DIR}/" 2>&1 || gcloud storage cp "${GCS_RUN_DIR}/*" "${ITER_DIR}/" 2>&1 || true
  else
    echo "Fallback searching for any run files matching ${RUN_TAG}..."
    gcloud storage cp -r "${DEST}/runs/${TEST_NAME}/*/*/*${RUN_TAG}/*" "${ITER_DIR}/" 2>&1 || true
  fi

  # Parse results for this iteration
  python3 - "${ITER_DIR}" "${TEST_NAME}" << 'EOF'
import csv
import json
import os
import sys
import glob

iter_dir = sys.argv[1]
test_name = sys.argv[2]

try:
    stats_files = glob.glob(os.path.join(iter_dir, "*stats.csv"))
    if not stats_files:
        stats_files = glob.glob(os.path.join(iter_dir, f"{test_name}_stats.csv"))

    metrics = {
        "ttfi_p90_ms": 0.0,
        "ttfi_p95_ms": 0.0,
        "suspend_actor_p95_ms": 0.0,
    }
    constraints = {
        "error_rate": 0.0,
        "node_oom_events": 0,
        "client_send_rate_ratio": 1.0,
    }
    raw_stats = []

    total_requests = 0
    total_failures = 0

    if stats_files and os.path.exists(stats_files[0]):
        with open(stats_files[0], "r") as f:
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
        with open(dmesg_file, "r") as f:
            content = f.read()
            oom_events = content.lower().count("oom-killer") + content.lower().count("out of memory")
    constraints["node_oom_events"] = oom_events

    cpu_top_file = os.path.join(iter_dir, "profiles", "cpu_top.txt")
    cpu_hotspots = []
    if os.path.exists(cpu_top_file):
        with open(cpu_top_file, "r") as f:
            lines = f.readlines()
        for line in lines[8:20]:
            parts = line.strip().split()
            if len(parts) >= 6:
                cpu_hotspots.append({
                    "flat": parts[0],
                    "flat_pct": parts[1],
                    "cum": parts[3],
                    "cum_pct": parts[4],
                    "symbol": " ".join(parts[5:])
                })

    summary = {
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

    with open(os.path.join(iter_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Successfully generated {iter_dir}/summary.json with TTFI metrics:", metrics)

except Exception as e:
    with open(os.path.join(iter_dir, "error.json"), "w") as f:
        json.dump({"error": str(e), "stage": "iter_post_processing"}, f, indent=2)
    print(f"Error processing iteration results: {e}")
EOF

done

echo "=== Consolidating & Aggregating Metrics across ${BENCHMARK_ITERATIONS} Iteration(s) ==="

python3 - "${RESULTS_DIR}" "${BENCHMARK_ITERATIONS}" << 'EOF'
import json
import os
import shutil
import sys

results_dir = sys.argv[1]
iterations = int(sys.argv[2])

iter_summaries = []
for i in range(1, iterations + 1):
    iter_file = os.path.join(results_dir, f"iter_{i}", "summary.json")
    if os.path.exists(iter_file):
        try:
            with open(iter_file, "r") as f:
                data = json.load(f)
                if data.get("metrics", {}).get("ttfi_p90_ms", 0.0) > 0:
                    iter_summaries.append((i, data))
                else:
                    print(f"Warning: {iter_file} contains zeroed metrics: {data.get('metrics')}")
        except Exception as e:
            print(f"Warning: Could not read {iter_file}: {e}")

if not iter_summaries:
    print("Error: No valid iteration summaries found to aggregate.")
    with open(os.path.join(results_dir, "error.json"), "w") as f:
        json.dump({"error": "No valid iteration summaries found", "stage": "aggregation"}, f, indent=2)
    sys.exit(1)

# Sort iterations by primary objective (ttfi_p90_ms ascending)
iter_summaries.sort(key=lambda item: item[1].get("metrics", {}).get("ttfi_p90_ms", float("inf")))
median_idx, median_summary = iter_summaries[len(iter_summaries) // 2]
print(f"Selected median iteration: iter_{median_idx}")

# Copy artifacts from the median iteration to top-level results_dir
median_iter_dir = os.path.join(results_dir, f"iter_{median_idx}")
for fname in [
    "stats.csv",
    "stats_history.csv",
    "failures.csv",
    "exceptions.csv",
    "logs.txt",
    "traces.txt",
    "status.json",
    "stats.jsonl",
]:
    src = os.path.join(median_iter_dir, fname)
    dst = os.path.join(results_dir, fname)
    if os.path.exists(src):
        shutil.copy2(src, dst)

median_profiles_dir = os.path.join(median_iter_dir, "profiles")
dst_profiles_dir = os.path.join(results_dir, "profiles")
if os.path.exists(median_profiles_dir):
    for pf in os.listdir(median_profiles_dir):
        shutil.copy2(os.path.join(median_profiles_dir, pf), os.path.join(dst_profiles_dir, pf))

top_summary = {
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
with open(target_summary_path, "w") as f:
    json.dump(top_summary, f, indent=2)

print(f"Generated aggregated {target_summary_path} successfully (median iteration: {median_idx}).")
print(json.dumps(top_summary["metrics"], indent=2))
EOF
chmod +x "${APO_DIR}/run_experiment.sh"
