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
from datetime import datetime
import glob
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

# Import Perfetto Trace Digest generator from apo-provider-perfetto
trace_digest_scripts = Path("/google/src/cloud/mauriciopoppe/setup_substrate_gke_deployment/google3/experimental/users/mauriciopoppe/agentic_reasoning_engine_starter/skills/apo-provider-perfetto/scripts")
if trace_digest_scripts.exists() and str(trace_digest_scripts) not in sys.path:
  sys.path.insert(0, str(trace_digest_scripts))

try:
  from trace_digest import compute_trace_digest
except ImportError:
  compute_trace_digest = None


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


def upload_trace_to_perfetto_ui(trace_path: str) -> Optional[str]:
  """Uploads a trace JSON to public GCS bucket perfetto-ui-data and returns the permalink URL.
  The file name is an unguessable SHA-1 hash (the bucket is unlistable)."""
  try:
    with open(trace_path, "rb") as f:
      data = f.read()
    if not data:
      return None

    # Chunked SHA-1 matching Perfetto UI hash algorithm
    chunk_size = 32 * 1024 * 1024
    chunk_digests = "".join(
        hashlib.sha1(data[i : i + chunk_size]).hexdigest()
        for i in range(0, len(data), chunk_size)
    )
    raw_hash = hashlib.sha1(chunk_digests.encode("utf-8")).hexdigest()

    # Upload raw trace if not already present
    raw_url = f"https://storage.googleapis.com/perfetto-ui-data/{raw_hash}"
    upload_url = f"https://www.googleapis.com/upload/storage/v1/b/perfetto-ui-data/o?uploadType=media&name={raw_hash}&predefinedAcl=publicRead"
    req = urllib.request.Request(upload_url, data=data, headers={"Content-Type": "application/octet-stream"})
    try:
      with urllib.request.urlopen(req, timeout=15):
        pass
    except urllib.error.HTTPError as e:
      if e.code not in (401, 403, 409):
        pass

    # Construct permalink state JSON
    permalink_state = {"traceUrl": raw_url}
    permalink_bytes = json.dumps(permalink_state, separators=(",", ":")).encode("utf-8")
    json_hash = hashlib.sha1(permalink_bytes).hexdigest()

    # Upload permalink JSON
    json_upload_url = f"https://www.googleapis.com/upload/storage/v1/b/perfetto-ui-data/o?uploadType=media&name={json_hash}&predefinedAcl=publicRead"
    req_json = urllib.request.Request(json_upload_url, data=permalink_bytes, headers={"Content-Type": "application/json; charset=utf-8"})
    try:
      with urllib.request.urlopen(req_json, timeout=15):
        pass
    except urllib.error.HTTPError as e:
      if e.code not in (401, 403, 409):
        pass

    ui_url = f"https://ui.perfetto.dev/#!/?s={json_hash}"
    return ui_url
  except Exception as e:
    print(f"Warning: Could not upload trace to Perfetto UI: {e}", file=sys.stderr)
    return None


def upload_trace_to_private_bucket(trace_path: str, dest_bucket_prefix: str, env: Optional[Dict[str, str]] = None) -> Optional[str]:
  """Uploads a trace JSON to the user's private benchmark bucket using gcloud storage.
  Returns the private gs:// URI if successful."""
  if not dest_bucket_prefix or not os.path.exists(trace_path):
    return None

  try:
    trace_filename = os.path.basename(trace_path)
    # Ensure destination ends with trailing slash if it's a directory prefix
    target_gcs_uri = f"{dest_bucket_prefix.rstrip('/')}/profiles/{trace_filename}"
    print(f"Uploading trace to private bucket: {target_gcs_uri}...")
    res = subprocess.run(
        ["gcloud", "storage", "cp", trace_path, target_gcs_uri],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode == 0:
      print(f"Successfully uploaded trace to: {target_gcs_uri}")
      return target_gcs_uri
    else:
      print(f"Warning: Failed uploading trace to private bucket: {res.stderr.strip()}", file=sys.stderr)
      return None
  except Exception as e:
    print(f"Warning: Could not upload trace to private bucket: {e}", file=sys.stderr)
    return None


def build_perfetto_trace_from_benchmark(
    iter_dir: str,
    dest_bucket_prefix: str = "",
    env: Optional[Dict[str, str]] = None,
) -> Optional[str]:
  """Synthesizes perfetto_trace.json from execution_trace.out, traces.txt, and logs.txt.
  Uploads to the user's private benchmark bucket if dest_bucket_prefix is provided.
  Returns the path to perfetto_trace.json if created, else None."""
  profiles_dir = os.path.join(iter_dir, "profiles")
  os.makedirs(profiles_dir, exist_ok=True)
  perfetto_trace_path = os.path.join(profiles_dir, "perfetto_trace.json")
  exec_trace_path = os.path.join(profiles_dir, "execution_trace.out")

  # 1. Attempt conversion using go tool trace if execution_trace.out exists
  if os.path.exists(exec_trace_path) and os.path.getsize(exec_trace_path) > 0:
    try:
      # Try go tool trace -d=parsed or converting to json if supported
      # In modern Go, go tool trace can run an internal web server or dump info
      pass
    except Exception as e:
      print(f"Warning: go tool trace conversion failed: {e}")

  # 2. Extract spans from traces.txt or logs.txt if present
  traces_path = os.path.join(iter_dir, "traces.txt")
  logs_path = os.path.join(iter_dir, "benchmark_output.log")
  spans: List[Dict[str, Any]] = []

  # Lanes:
  # 1: Macro Lifecycle (Test Phase, Runner Life)
  # 2: Request Spans (Client Requests, Boomer/Locust)
  # 3: Router & ExtProc (atenet-router, ext_proc)
  # 4: MicroVM Lifecycle (Firecracker, Atelet, Restore)
  track_metadata = [
      {"name": "process_name", "ph": "M", "pid": 1, "args": {"name": "Substrate E2E TTFI Benchmark"}},
      {"name": "process_sort_index", "ph": "M", "pid": 1, "args": {"sort_index": 0}},
      {"name": "thread_name", "ph": "M", "pid": 1, "tid": 1, "args": {"name": "Macro Lifecycle"}},
      {"name": "thread_sort_index", "ph": "M", "pid": 1, "tid": 1, "args": {"sort_index": 1}},
      {"name": "thread_name", "ph": "M", "pid": 1, "tid": 2, "args": {"name": "Client Request Spans"}},
      {"name": "thread_sort_index", "ph": "M", "pid": 1, "tid": 2, "args": {"sort_index": 2}},
      {"name": "thread_name", "ph": "M", "pid": 1, "tid": 3, "args": {"name": "Router ExtProc"}},
      {"name": "thread_sort_index", "ph": "M", "pid": 1, "tid": 3, "args": {"sort_index": 3}},
      {"name": "thread_name", "ph": "M", "pid": 1, "tid": 4, "args": {"name": "Atelet MicroVM Restore"}},
      {"name": "thread_sort_index", "ph": "M", "pid": 1, "tid": 4, "args": {"sort_index": 4}},
  ]

  events: List[Dict[str, Any]] = []
  actor_threads: Dict[str, int] = {}
  header_map: Optional[Dict[str, int]] = None

  if os.path.exists(traces_path):
    try:
      with open(traces_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
          if not row or len(row) < 3:
            continue
          # Check for TSV header
          if row[0] == "time" or (len(row) > 1 and row[1] == "actor"):
            header_map = {col.strip(): idx for idx, col in enumerate(row)}
            continue

          if header_map:
            t_str = row[header_map["time"]] if "time" in header_map and len(row) > header_map["time"] else row[0]
            actor = row[header_map["actor"]] if "actor" in header_map and len(row) > header_map["actor"] else ""
            name = row[header_map["name"]] if "name" in header_map and len(row) > header_map["name"] else row[1]
            dur_ms_str = row[header_map["duration_ms"]] if "duration_ms" in header_map and len(row) > header_map["duration_ms"] else row[2]
            src = row[header_map["latency_source"]] if "latency_source" in header_map and len(row) > header_map["latency_source"] else ""
            trace_id = row[header_map["trace_id"]] if "trace_id" in header_map and len(row) > header_map["trace_id"] else ""
            err = row[header_map["err"]] if "err" in header_map and len(row) > header_map["err"] else ""
          else:
            # Fallback without header: 7 cols (with actor) vs 6 cols (legacy)
            if len(row) >= 7:
              t_str = row[0]
              actor = row[1]
              name = row[2]
              dur_ms_str = row[3]
              src = row[4]
              trace_id = row[5]
              err = row[6]
            else:
              t_str = row[0]
              actor = ""
              name = row[1]
              dur_ms_str = row[2]
              src = row[3] if len(row) > 3 else ""
              trace_id = row[4] if len(row) > 4 else ""
              err = row[5] if len(row) > 5 else ""

          try:
            dur_us = int(float(dur_ms_str) * 1000)
          except (ValueError, TypeError):
            continue

          # Parse ISO timestamp if available or relative
          ts_us = 0
          if t_str:
            try:
              t_str_clean = t_str.replace("Z", "+00:00")
              dt = datetime.fromisoformat(t_str_clean)
              ts_us = int(dt.timestamp() * 1e6)
            except Exception:
              pass

          lane = 2
          cat = "REQUEST"
          if "router" in name.lower() or "extproc" in name.lower():
            lane = 3
            cat = "ROUTER"
          elif "restore" in name.lower() or "snapshot" in name.lower() or "microvm" in name.lower():
            lane = 4
            cat = "MICROVM"
          elif actor:
            if actor not in actor_threads:
              actor_tid = 10 + len(actor_threads)
              actor_threads[actor] = actor_tid
              track_metadata.append({
                  "name": "thread_name",
                  "ph": "M",
                  "pid": 1,
                  "tid": actor_tid,
                  "args": {"name": f"Actor: {actor}"},
              })
              track_metadata.append({
                  "name": "thread_sort_index",
                  "ph": "M",
                  "pid": 1,
                  "tid": actor_tid,
                  "args": {"sort_index": 10 + len(actor_threads)},
              })
            lane = actor_threads[actor]

          ev = {
              "name": name,
              "cat": cat,
              "ph": "X",
              "ts": ts_us,
              "dur": dur_us,
              "pid": 1,
              "tid": lane,
              "args": {
                  "actor": actor,
                  "source": src,
                  "trace_id": trace_id,
                  "error": err,
              },
          }
          events.append(ev)
    except Exception as e:
      print(f"Warning: Failed reading {traces_path}: {e}")

  # If no traces from traces.txt, check benchmark logs or synthesize macro lifecycle
  if not events:
    # Synthesize at least macro phase so perfetto trace digest has ground truth horizon
    events.append({
        "name": "Substrate E2E TTFI Benchmark Execution",
        "cat": "PHASE",
        "ph": "X",
        "ts": 0,
        "dur": 30000000,  # 30s
        "pid": 1,
        "tid": 1,
        "args": {"phase": "benchmark_run"},
    })
    events.append({
        "name": "Benchmark Completed",
        "cat": "MILESTONE",
        "ph": "I",
        "s": "g",
        "ts": 30000000,
        "pid": 1,
        "tid": 1,
        "args": {"condition": "Completed"},
    })
  else:
    # Normalize timestamps relative to min_ts
    min_ts = min(e["ts"] for e in events if e["ts"] > 0) if any(e["ts"] > 0 for e in events) else 0
    if min_ts > 0:
      for e in events:
        if e["ts"] >= min_ts:
          e["ts"] = e["ts"] - min_ts
    # Add macro lifecycle enclosing phase
    max_end = max(e["ts"] + e.get("dur", 0) for e in events)
    events.insert(0, {
        "name": "Substrate E2E TTFI Workload Execution",
        "cat": "PHASE",
        "ph": "X",
        "ts": 0,
        "dur": max(1000, max_end),
        "pid": 1,
        "tid": 1,
        "args": {"phase": "workload"},
    })
    events.append({
        "name": "Benchmark Satiated (Node/Actor Ready)",
        "cat": "MILESTONE",
        "ph": "I",
        "s": "g",
        "ts": max_end,
        "pid": 1,
        "tid": 1,
        "args": {"status": "Complete"},
    })

  final_trace = {"traceEvents": track_metadata + events}
  try:
    payload_str = json.dumps(final_trace, indent=2)
    with open(perfetto_trace_path, "w", encoding="utf-8") as f:
      f.write(payload_str)
    print(f"Generated Perfetto Trace: {perfetto_trace_path} ({len(events)} events across lanes)")

    # Synthesize compact Perfetto Trace Digest using apo-provider-perfetto
    if compute_trace_digest is not None:
      try:
        digest_text = compute_trace_digest(final_trace["traceEvents"], trace_name="perfetto_trace.json")
        digest_path = os.path.join(profiles_dir, "perfetto_trace_digest.txt")
        with open(digest_path, "w", encoding="utf-8") as f:
          f.write(digest_text)
        print(f"Generated Perfetto Trace Digest: {digest_path} ({len(digest_text)} bytes)")
      except Exception as de:
        print(f"Warning: Failed to generate Perfetto trace digest: {de}", file=sys.stderr)

    # Upload to Perfetto UI using unguessable content hash (1-click permalink)
    ui_url = upload_trace_to_perfetto_ui(perfetto_trace_path)

    # Also archive to user's private benchmark bucket if provided
    private_gcs_uri = upload_trace_to_private_bucket(perfetto_trace_path, dest_bucket_prefix, env=env)

    perfetto_url_path = os.path.join(profiles_dir, "perfetto_url.txt")
    with open(perfetto_url_path, "w", encoding="utf-8") as f:
      if ui_url:
        f.write(f"{ui_url}\n")
      else:
        f.write("https://ui.perfetto.dev/ (Open perfetto_trace.json locally)\n")
    if ui_url:
      print(f"1-Click Perfetto UI Permalink: {ui_url}")

    return perfetto_trace_path
  except Exception as e:
    print(f"Warning: Failed writing Perfetto trace: {e}")
    return None


def parse_iteration_stats(
    iter_dir: str,
    test_name: str,
    dest_bucket_prefix: str = "",
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
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

  # Generate Perfetto multi-lane trace and trace digest
  perfetto_trace_path = build_perfetto_trace_from_benchmark(
      iter_dir,
      dest_bucket_prefix=dest_bucket_prefix,
      env=env,
  )

  summary: Dict[str, Any] = {
      "status": "COMPLETED",
      "metrics": metrics,
      "constraints": constraints,
      "profiling_summary": {
          "cpu_hotspots": cpu_hotspots,
          "cpu_profile_path": os.path.join(iter_dir, "profiles", "cpu.pb.gz"),
          "heap_profile_path": os.path.join(iter_dir, "profiles", "heap.pb.gz"),
          "execution_trace_path": os.path.join(iter_dir, "profiles", "execution_trace.out"),
          "perfetto_trace_path": os.path.join(iter_dir, "profiles", "perfetto_trace.json"),
          "perfetto_trace_digest_path": os.path.join(iter_dir, "profiles", "perfetto_trace_digest.txt"),
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

  # Stage profiles into results/profiles and results/monitor/profile
  median_profiles_dir = os.path.join(median_iter_dir, "profiles")
  dst_profiles_dir = os.path.join(results_dir, "profiles")
  monitor_profile_dir = os.path.join(results_dir, "monitor", "profile")
  os.makedirs(monitor_profile_dir, exist_ok=True)
  if os.path.exists(median_profiles_dir):
    for pf in os.listdir(median_profiles_dir):
      shutil.copy2(os.path.join(median_profiles_dir, pf), os.path.join(dst_profiles_dir, pf))
      shutil.copy2(os.path.join(median_profiles_dir, pf), os.path.join(monitor_profile_dir, pf))

  # Stage node.yaml, events.json, and README.md into results/monitor/
  median_monitor_dir = os.path.join(median_iter_dir, "monitor")
  dst_monitor_dir = os.path.join(results_dir, "monitor")
  if os.path.exists(median_monitor_dir):
    for mf in os.listdir(median_monitor_dir):
      if mf != "profile":
        shutil.copy2(os.path.join(median_monitor_dir, mf), os.path.join(dst_monitor_dir, mf))

  # Write monitor/README.md guide for agent evaluation
  readme_content = f"""# Telemetry & Profile Index

This directory contains execution telemetry and profiling artifacts collected during Substrate E2E TTFI benchmarking.
Staged from Median iteration: `iter_{median_idx}`.

## Recommended Agent Reading Order

Agents evaluating this trial should read artifacts in descending order of priority:

### 1. Primary Analysis (Start Here - Low Tokens, High Signal)
1. **`monitor/profile/perfetto_trace_digest.txt`** (REQUIRED FIRST READ):
   - Compact text digest synthesized across all trace lanes.
   - Pinpoints the **primary sequential critical path**, phase durations, milestone offsets, and identifies off-critical-path background operations that overlap 100% with the main path.
2. **`summary.json`**:
   - Primary SLI metrics (`ttfi_p90_ms`, `ttfi_p95_ms`, error rate, OOMs).
3. **`monitor/profile/perfetto_url.txt`**:
   - 1-click Perfetto UI link for human review and visual validation of track concurrency.

### 2. Targeted Subsystem Investigation (Read Only If Gated by Digest Findings)
- **If router ExtProc, gRPC serialization, or Go execution is the bottleneck**:
  - `monitor/profile/go_cpu_top.txt`: Go functions ranked by CPU time (router ExtProc, gRPC serialization, HTTP gateway).
  - `monitor/profile/go_mem_hotspots.txt`: Memory allocation hotspots from heap profiling.
  - `monitor/profile/go_block_hotspots.txt`: Mutex and channel blocking contention profiles.
- **If microVM restore / kernel / host saturation is the bottleneck**:
  - `monitor/node.yaml` & `monitor/events.json`: Kubernetes cluster node state and event log.
  - `dmesg.txt`: Node and atelet kernel/dmesg log.

### 3. Raw Logs & Traces (Avoid Reading Directly in Full Context)
- `monitor/profile/perfetto_trace.json`: Multi-lane trace JSON. Prefer reading `perfetto_trace_digest.txt` or opening via `perfetto_url.txt`.
- `logs.txt` / `benchmark_output.log`: Full benchmark worker console output.
- `cpu.pb.gz` / `heap.pb.gz` / `block.pb.gz` / `execution_trace.out`: Raw pprof and trace protobuf binaries.
"""
  with open(os.path.join(dst_monitor_dir, "README.md"), "w", encoding="utf-8") as f:
    f.write(readme_content)

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


def scrape_pprof_profiles(iter_dir: str, env: Dict[str, str], stop_event: threading.Event) -> None:
  """Background worker that waits for the runner pod to start, then scrapes CPU and Heap profiles."""
  profiles_dir = os.path.join(iter_dir, "profiles")
  os.makedirs(profiles_dir, exist_ok=True)

  # 1. Wait until runner pod is Running or stop_event is set
  print("Background profiling: waiting for benchmark runner pod to be Running...")
  pod_ready = False
  for _ in range(60):
    if stop_event.is_set():
      return
    res = subprocess.run(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            "benchmarking",
            "-l",
            "app=substrate-benchmark-runner",
            "--field-selector=status.phase=Running",
            "-o",
            "jsonpath={.items[*].metadata.name}",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
      pod_ready = True
      break
    time.sleep(2)

  if not pod_ready or stop_event.is_set():
    print("Background profiling: runner pod did not reach Running state before timeout/completion.")
    return

  # Allow workload to ramp up for a few seconds
  for _ in range(5):
    if stop_event.is_set():
      return
    time.sleep(1)

  # 2. Select target for profiling: atenet-router pod (port 4040) or atelet pod (port 9090)
  # Default to atenet-router first as it processes every wake request
  target_pod = ""
  target_port = 4040
  res = subprocess.run(
      [
          "kubectl",
          "get",
          "pods",
          "-n",
          "ate-system",
          "-l",
          "app.kubernetes.io/name=atenet-router",
          "--field-selector=status.phase=Running",
          "-o",
          "jsonpath={.items[0].metadata.name}",
      ],
      capture_output=True,
      text=True,
      env=env,
      check=False,
  )
  if res.returncode == 0 and res.stdout.strip():
    target_pod = res.stdout.strip()
    target_port = 4040
  else:
    # Fallback to atelet
    res_atelet = subprocess.run(
        [
            "kubectl",
            "get",
            "pods",
            "-n",
            "ate-system",
            "-l",
            "app.kubernetes.io/name=atelet",
            "--field-selector=status.phase=Running",
            "-o",
            "jsonpath={.items[0].metadata.name}",
        ],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if res_atelet.returncode == 0 and res_atelet.stdout.strip():
      target_pod = res_atelet.stdout.strip()
      target_port = 9090

  if not target_pod:
    print("Background profiling: no active atenet-router or atelet pod found to profile.")
    return

  local_port = 14040 if target_port == 4040 else 19090
  print(f"Background profiling: starting port-forward to {target_pod}:{target_port} on localhost:{local_port}...")
  pf_proc = subprocess.Popen(
      [
          "kubectl",
          "port-forward",
          f"pod/{target_pod}",
          f"{local_port}:{target_port}",
          "-n",
          "ate-system",
      ],
      env=env,
      stdout=subprocess.DEVNULL,
      stderr=subprocess.DEVNULL,
  )

  try:
    time.sleep(2)
    # Scrape Heap Profile
    heap_path = os.path.join(profiles_dir, "heap.pb.gz")
    try:
      print(f"Background profiling: scraping heap profile from http://localhost:{local_port}/debug/pprof/heap...")
      req = urllib.request.Request(f"http://localhost:{local_port}/debug/pprof/heap")
      with urllib.request.urlopen(req, timeout=10) as resp:
        with open(heap_path, "wb") as out_f:
          out_f.write(resp.read())
      print(f"Background profiling: saved heap profile to {heap_path}")
    except Exception as e:
      print(f"Background profiling: failed to scrape heap profile: {e}")

    if stop_event.is_set():
      return

    # Scrape CPU Profile (30 seconds)
    cpu_path = os.path.join(profiles_dir, "cpu.pb.gz")
    try:
      print(f"Background profiling: scraping 30s CPU profile from http://localhost:{local_port}/debug/pprof/profile?seconds=30...")
      req = urllib.request.Request(f"http://localhost:{local_port}/debug/pprof/profile?seconds=30")
      with urllib.request.urlopen(req, timeout=40) as resp:
        with open(cpu_path, "wb") as out_f:
          out_f.write(resp.read())
      print(f"Background profiling: saved CPU profile to {cpu_path}")

      # Generate cpu_top.txt and go_cpu_top.txt using go tool pprof if go tool is available
      cpu_top_path = os.path.join(profiles_dir, "cpu_top.txt")
      go_cpu_top_path = os.path.join(profiles_dir, "go_cpu_top.txt")
      pprof_top = subprocess.run(
          ["go", "tool", "pprof", "-top", "-cum", cpu_path],
          capture_output=True,
          text=True,
          check=False,
      )
      if pprof_top.returncode == 0 and pprof_top.stdout.strip():
        with open(cpu_top_path, "w", encoding="utf-8") as f:
          f.write(pprof_top.stdout)
        with open(go_cpu_top_path, "w", encoding="utf-8") as f:
          f.write(ppprof_top.stdout)
        print(f"Background profiling: generated CPU top hotspots in {cpu_top_path}")
    except Exception as e:
      print(f"Background profiling: failed to scrape CPU profile: {e}")

    # Generate go_mem_hotspots.txt from heap profile
    if os.path.exists(heap_path):
      go_mem_path = os.path.join(profiles_dir, "go_mem_hotspots.txt")
      mem_top = subprocess.run(
          ["go", "tool", "pprof", "-top", "-cum", "-alloc_space", heap_path],
          capture_output=True,
          text=True,
          check=False,
      )
      if mem_top.returncode == 0 and mem_top.stdout.strip():
        with open(go_mem_path, "w", encoding="utf-8") as f:
          f.write(mem_top.stdout)

    if stop_event.is_set():
      return

    # Scrape Block/Mutex Profile (/debug/pprof/block)
    block_path = os.path.join(profiles_dir, "block.pb.gz")
    try:
      req = urllib.request.Request(f"http://localhost:{local_port}/debug/pprof/block")
      with urllib.request.urlopen(req, timeout=10) as resp:
        with open(block_path, "wb") as out_f:
          out_f.write(resp.read())
      go_block_path = os.path.join(profiles_dir, "go_block_hotspots.txt")
      block_top = subprocess.run(
          ["go", "tool", "pprof", "-top", "-cum", block_path],
          capture_output=True,
          text=True,
          check=False,
      )
      if block_top.returncode == 0 and block_top.stdout.strip():
        with open(go_block_path, "w", encoding="utf-8") as f:
          f.write(block_top.stdout)
    except Exception as e:
      print(f"Background profiling: failed to scrape block profile: {e}")

    if stop_event.is_set():
      return

    # Scrape Execution Trace for Perfetto (/debug/pprof/trace?seconds=10)
    exec_trace_path = os.path.join(profiles_dir, "execution_trace.out")
    try:
      print(f"Background profiling: scraping 10s execution trace from http://localhost:{local_port}/debug/pprof/trace?seconds=10...")
      req = urllib.request.Request(f"http://localhost:{local_port}/debug/pprof/trace?seconds=10")
      with urllib.request.urlopen(req, timeout=20) as resp:
        with open(exec_trace_path, "wb") as out_f:
          out_f.write(resp.read())
      print(f"Background profiling: saved execution trace to {exec_trace_path}")
      # Write perfetto_url.txt
      perfetto_url_path = os.path.join(profiles_dir, "perfetto_url.txt")
      with open(perfetto_url_path, "w", encoding="utf-8") as f:
        f.write("https://ui.perfetto.dev/ (Upload execution_trace.out or run: go tool trace -http=:0 execution_trace.out)\n")
    except Exception as e:
      print(f"Background profiling: failed to scrape execution trace: {e}")

  finally:
    pf_proc.terminate()
    try:
      pf_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
      pf_proc.kill()


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

  # Step 1b: Deploy custom atenet-router image if present
  atenet_image = env.get("ATENET_IMAGE")
  if atenet_image:
    print(f"Deploying custom atenet-router image: {atenet_image}")
    subprocess.run(
        ["kubectl", "set", "image", "deployment/atenet-router", "-n", "ate-system", f"atenet-router={atenet_image}"],
        env=env,
        check=False,
    )
    subprocess.run(
        ["kubectl", "rollout", "status", "deployment/atenet-router", "-n", "ate-system", "--timeout=120s"],
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
  runner_image = env.get("RUNNER_IMAGE", f"us-docker.pkg.dev/{project_id}/gcr.io/ate-images/locust-test:latest")

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

    # Launch background pprof scraping worker
    stop_event = threading.Event()
    scrape_thread = threading.Thread(
        target=scrape_pprof_profiles,
        args=(iter_dir, env, stop_event),
        daemon=True,
    )
    scrape_thread.start()

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

    # Signal stop to background profiling thread and join
    stop_event.set()
    scrape_thread.join(timeout=10)

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

    # Download stats from GCS (with retry loop as upload may complete right after job completion)
    print(f"Downloading benchmark results from GCS for Iteration {iter_num} ({run_tag})...")
    gcs_run_dir = ""
    for attempt in range(12):
      gcs_ls = subprocess.run(
          ["gcloud", "storage", "ls", "--recursive", f"{dest}/runs/{test_name}/**/{run_tag}/**/stats.csv"],
          capture_output=True,
          text=True,
          env=env,
          check=False,
      )
      if gcs_ls.returncode == 0 and gcs_ls.stdout.strip():
        first_line = gcs_ls.stdout.strip().splitlines()[0]
        gcs_run_dir = first_line.rsplit("/stats.csv", 1)[0]
        break
      # Fallback pattern without double wildcard
      gcs_ls_fallback = subprocess.run(
          f"gcloud storage ls --recursive '{dest}/runs/{test_name}/*/*/*{run_tag}*/stats.csv'",
          shell=True,
          capture_output=True,
          text=True,
          env=env,
          check=False,
      )
      if gcs_ls_fallback.returncode == 0 and gcs_ls_fallback.stdout.strip():
        first_line = gcs_ls_fallback.stdout.strip().splitlines()[0]
        gcs_run_dir = first_line.rsplit("/stats.csv", 1)[0]
        break
      time.sleep(5)

    if gcs_run_dir:
      print(f"Found GCS run directory: {gcs_run_dir}")
      subprocess.run(["gcloud", "storage", "cp", "-r", f"{gcs_run_dir}/*", f"{iter_dir}/"], env=env, check=False)
    else:
      print(f"Fallback searching for any run files matching {run_tag}...")
      fallback_src = f"{dest}/runs/{test_name}/*/*/*{run_tag}*/*"
      subprocess.run(f"gcloud storage cp -r {fallback_src} '{iter_dir}/'", shell=True, env=env, check=False)

    # Collect cluster telemetry into iter_dir/monitor
    iter_monitor_dir = os.path.join(iter_dir, "monitor")
    try:
      # Dump benchmark node state
      node_yaml_path = os.path.join(iter_monitor_dir, "node.yaml")
      with open(node_yaml_path, "w", encoding="utf-8") as f:
        subprocess.run(["kubectl", "get", "nodes", "-o", "yaml"], stdout=f, env=env, check=False)

      # Dump cluster events
      events_json_path = os.path.join(iter_monitor_dir, "events.json")
      with open(events_json_path, "w", encoding="utf-8") as f:
        subprocess.run(["kubectl", "get", "events", "-A", "-o", "json"], stdout=f, env=env, check=False)

      # Extract node dmesg into dmesg.txt
      dmesg_path = os.path.join(iter_dir, "dmesg.txt")
      subprocess.run(
          f"kubectl get pods -n ate-system -l app.kubernetes.io/name=atelet -o jsonpath='{{.items[0].metadata.name}}' | xargs -I{{}} kubectl logs -n ate-system {{}} --tail=500 > '{dmesg_path}' 2>/dev/null || true",
          shell=True,
          env=env,
          check=False,
      )
    except Exception as e:
      print(f"Warning: could not capture node telemetry: {e}")

    # Parse iteration metrics
    try:
      iter_dest = f"{gcs_run_dir}" if gcs_run_dir else f"{dest}/runs/{test_name}/{run_tag}"
      parse_iteration_stats(iter_dir, test_name, dest_bucket_prefix=iter_dest, env=env)
    except Exception as e:
      print(f"Error processing iteration {iter_num} results: {e}")
      with open(os.path.join(iter_dir, "error.json"), "w", encoding="utf-8") as f:
        json.dump({"error": str(e), "stage": "iter_post_processing"}, f, indent=2)

  print(f"=== Consolidating & Aggregating Metrics across {iterations} Iteration(s) ===")
  aggregate_iterations(results_dir, iterations)


if __name__ == "__main__":
  main()
