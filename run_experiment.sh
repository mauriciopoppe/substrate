#!/bin/bash
# ==============================================================================
# WorkQueue Benchmark Execution Script for Agent Substrate Ingress Routing
# Conforms to the APO Benchmark Execution Contract:
# 1. Accepts $1 as <RESULTS_DIR>
# 2. Writes shell PID $! to <RESULTS_DIR>/monitor/benchmark.pid
# 3. Streams stdout/stderr to <RESULTS_DIR>/benchmark_output.log
# 4. Deploys custom atenet-router image built by build.sh
# 5. Captures pprof CPU and heap profiles during active load
# 6. Writes clean metrics to <RESULTS_DIR>/summary.json or diagnostic errors to <RESULTS_DIR>/error.json
# ==============================================================================

set -euo pipefail

RESULTS_DIR="${1:-results/scratch}"
mkdir -p "${RESULTS_DIR}/monitor" "${RESULTS_DIR}/profiles"

WORKSPACE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
cd "${WORKSPACE_DIR}"

# Source runtime environment if available
if [ -f "${WORKSPACE_DIR}/set-env.sh" ]; then
  # shellcheck disable=SC1091
  source "${WORKSPACE_DIR}/set-env.sh"
fi

echo "Starting Agent Substrate Ingress Benchmark execution in ${WORKSPACE_DIR}..."

# Source tunables
if [ -f "${WORKSPACE_DIR}/manifests/tunables.env" ]; then
  # shellcheck disable=SC1091
  source "${WORKSPACE_DIR}/manifests/tunables.env"
fi

# Step 0: Ensure idempotency by cleaning up stale resources from previous benchmark runs
echo "Ensuring cluster is clean from previous benchmark runs (idempotency check)..."
# 0a. Delete any stale benchmark runner Jobs or Pods in benchmarking namespace
kubectl delete jobs,pods -n benchmarking --all --wait=false 2>/dev/null || true

# 0b. Purge leftover benchmark actors from Substrate database so warming starts clean
kubectl exec -n ate-system pod/postgres-0 -c postgres -- \
  psql -U postgres -d atepg -q -c "
    DELETE FROM worker_assignments WHERE actor_uid IN (SELECT uid FROM actors WHERE atespace='ingress-benchmark');
    DELETE FROM actor_egress_policies WHERE atespace='ingress-benchmark';
    DELETE FROM actors WHERE atespace='ingress-benchmark';
  " 2>/dev/null || true

# Step 1: Deploy built atenet-router container image if present
if [ -f "${RESULTS_DIR}/build_artifacts.env" ]; then
  # shellcheck disable=SC1091
  source "${RESULTS_DIR}/build_artifacts.env"
fi

if [ -n "${ROUTER_IMAGE:-}" ]; then
  echo "Deploying custom atenet-router image: ${ROUTER_IMAGE}"
  kubectl set image deployment/atenet-router -n ate-system atenet-router="${ROUTER_IMAGE}"
fi

# Step 2: Forward feature flags from tunables.env to atenet-router
echo "Syncing feature flags from tunables.env into ConfigMap atenet-router-features..."
FEATURE_ENV_FILE="$(mktemp)"
if [ -f "${WORKSPACE_DIR}/manifests/tunables.env" ]; then
  grep -E '^(export )?FEATURE_[A-Za-z0-9_]+=' "${WORKSPACE_DIR}/manifests/tunables.env" | sed -E 's/^export //' > "${FEATURE_ENV_FILE}" || true
fi
if [ -s "${FEATURE_ENV_FILE}" ]; then
  kubectl create configmap atenet-router-features -n ate-system \
    --from-env-file="${FEATURE_ENV_FILE}" \
    --dry-run=client -o yaml | kubectl apply -f -
else
  kubectl create configmap atenet-router-features -n ate-system \
    --dry-run=client -o yaml | kubectl apply -f -
fi
rm -f "${FEATURE_ENV_FILE}"

# Step 3: Apply runtime environment flags and tunables patch
if [ -f "${WORKSPACE_DIR}/manifests/router-patch.yaml" ]; then
  echo "Applying router deployment patch with active tunables..."
  # Substitute tunables into patch
  envsubst < "${WORKSPACE_DIR}/manifests/router-patch.yaml" | kubectl patch deployment atenet-router -n ate-system --patch-file /dev/stdin 2>&1 || true
  kubectl rollout status deployment/atenet-router -n ate-system --timeout=180s 2>&1 || true
fi

# Step 3a: Force rollout restart of atenet-router to ensure fresh TLS certificates
echo "Restarting atenet-router deployment to refresh mTLS certificates..."
kubectl rollout restart deployment/atenet-router -n ate-system
kubectl rollout status deployment/atenet-router -n ate-system --timeout=180s

# Step 4: Run Substrate Nighthawk Ingress Benchmark driver
BENCH_SCRIPT="${WORKSPACE_DIR}/substrate/benchmarking/nighthawk-ingress/run-dev.sh"

if [ ! -f "${BENCH_SCRIPT}" ]; then
  cat <<EOF > "${RESULTS_DIR}/error.json"
{
  "status": "FAILED",
  "stage": "preflight",
  "error": "Benchmark script ${BENCH_SCRIPT} not found"
}
EOF
  exit 1
fi

export ENVOY_CPU="${ENVOY_CONCURRENCY:-2}"
export TAIL_LATENCY_SLO_MS=25
export ACTORS="${ACTORS:-50}"

echo "Executing Nighthawk ingress capacity benchmark..."

# Step 4: Background telemetry and pprof profiler collector
(
  # Wait for benchmark runner job to begin ramping traffic
  echo "Waiting for benchmark traffic ramp to begin profiling..."
  sleep 45

  # Forward router metrics/pprof port (:9090)
  PPROF_PORT=19090
  kubectl port-forward -n ate-system deployment/atenet-router "${PPROF_PORT}:9090" >/dev/null 2>&1 &
  PF_PID=$!

  # Ensure port-forward is cleaned up on exit
  trap 'kill ${PF_PID} 2>/dev/null || true' EXIT

  # Wait for port-forward to establish
  sleep 3

  # Capture 30s CPU profile during active load
  echo "Capturing 30-second CPU profile from router :${PPROF_PORT}/debug/pprof/profile..."
  curl -s "http://127.0.0.1:${PPROF_PORT}/debug/pprof/profile?seconds=30" -o "${RESULTS_DIR}/profiles/cpu.pb.gz" || true

  # Capture Heap profile
  echo "Capturing Heap profile from router :${PPROF_PORT}/debug/pprof/heap..."
  curl -s "http://127.0.0.1:${PPROF_PORT}/debug/pprof/heap" -o "${RESULTS_DIR}/profiles/heap.pb.gz" || true

  # Generate text top summaries if go/pprof available
  if [ -f "${RESULTS_DIR}/profiles/cpu.pb.gz" ] && command -v go >/dev/null 2>&1; then
    go tool pprof -top -cum "${RESULTS_DIR}/profiles/cpu.pb.gz" > "${RESULTS_DIR}/profiles/cpu_top.txt" 2>&1 || true
  fi
  if [ -f "${RESULTS_DIR}/profiles/heap.pb.gz" ] && command -v go >/dev/null 2>&1; then
    go tool pprof -top -cum "${RESULTS_DIR}/profiles/heap.pb.gz" > "${RESULTS_DIR}/profiles/heap_top.txt" 2>&1 || true
  fi
) &
PROFILER_PID=$!

# Execute the benchmark driver
"${BENCH_SCRIPT}" --envoy-cpu "${ENVOY_CPU}" --actors "${ACTORS}" --tail-latency-slo-ms "${TAIL_LATENCY_SLO_MS}" 2>&1 | tee -a "${RESULTS_DIR}/benchmark_output.log" || true

# Wait for background profiler if still active
wait "${PROFILER_PID}" 2>/dev/null || true

# Retrieve capacity.json from GCS if printed in benchmark output
CAP_GCS="$(grep -oE 'gs://[^ ]+/capacity\.json' "${RESULTS_DIR}/benchmark_output.log" 2>/dev/null | tail -1 || true)"
if [ -n "${CAP_GCS}" ]; then
  echo "Downloading capacity results from ${CAP_GCS} to ${RESULTS_DIR}/capacity.json..."
  gcloud storage cp "${CAP_GCS}" "${RESULTS_DIR}/capacity.json" 2>&1 || true
fi

# Step 5: Post-processing and structured metric extraction
python3 - "${RESULTS_DIR}" << 'EOF'
import json
import os
import sys

results_dir = sys.argv[1]

try:
    # Read capacity results if produced by Nighthawk benchmark
    capacity_file = os.path.join(results_dir, "capacity.json")
    if os.path.exists(capacity_file):
        with open(capacity_file, "r") as f:
            raw_capacity = json.load(f)
        
        slo_max_rps = float(raw_capacity.get("slo_max_rps", 0.0))
        lat_p95 = float(raw_capacity.get("p95_ms", raw_capacity.get("latency_p95_ms", 0.0)))
        extproc_dur = float(raw_capacity.get("extproc_routing_duration_p95_ms", 0.0))
        success_rate = float(raw_capacity.get("metric_nighthawk.builtin_success_rate", 1.0))
        err_5xx = 1.0 - success_rate
        tail_2sigma = float(raw_capacity.get("tail_latency_mean_plus_2sigma_ms", raw_capacity.get("p95_ms", 0.0)))
        client_ratio = float(raw_capacity.get("metric_nighthawk.builtin_send_rate", raw_capacity.get("client_send_rate_ratio", 1.0)))

        # Ingest top bottleneck functions from CPU profile if present
        cpu_top_file = os.path.join(results_dir, "profiles", "cpu_top.txt")
        cpu_hotspots = []
        if os.path.exists(cpu_top_file):
            with open(cpu_top_file, "r") as f:
                lines = f.readlines()
            for line in lines[8:20]: # Top 12 lines
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
            "metrics": {
                "slo_max_rps": slo_max_rps,
                "latency_p95_ms": lat_p95,
            },
            "constraints": {
                "http_5xx_rate": err_5xx,
                "tail_latency_mean_plus_2sigma_ms": tail_2sigma,
                "client_send_rate_ratio": client_ratio,
            },
            "profiling_summary": {
                "cpu_hotspots": cpu_hotspots,
                "cpu_profile_path": os.path.join(results_dir, "profiles", "cpu.pb.gz"),
                "heap_profile_path": os.path.join(results_dir, "profiles", "heap.pb.gz"),
            },
            "raw_summary": raw_capacity,
        }
        with open(os.path.join(results_dir, "summary.json"), "w") as f:
            json.dump(summary, f, indent=2)
        print("Successfully generated summary.json with metrics and profiling summary")
    else:
        summary = {
            "metrics": {
                "slo_max_rps": 0.0,
                "latency_p95_ms": 0.0,
            },
            "constraints": {
                "http_5xx_rate": 0.0,
                "tail_latency_mean_plus_2sigma_ms": 0.0,
                "client_send_rate_ratio": 1.0,
            },
            "profiling_summary": {},
            "raw_summary": {},
        }
        with open(os.path.join(results_dir, "summary.json"), "w") as f:
            json.dump(summary, f, indent=2)
except Exception as e:
    with open(os.path.join(results_dir, "error.json"), "w") as f:
        json.dump({"error": str(e), "stage": "post_processing"}, f, indent=2)
    sys.exit(1)
EOF
