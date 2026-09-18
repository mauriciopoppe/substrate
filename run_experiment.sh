#!/usr/bin/env bash
# ==============================================================================
# WorkQueue Benchmark Execution Script for Pure Go Microbenchmarks in GKE Pods
# Conforms to the APO Benchmark Execution Contract:
# 1. Accepts $1 as <RESULTS_DIR>, supports --iterations / -n (default: 3)
# 2. Writes shell PID $! to <RESULTS_DIR>/monitor/benchmark.pid
# 3. Creates a dedicated, isolated Runner Pod on the c3-standard-44 node
#    with Guaranteed QoS (Requests == Limits: 4 CPU, 8Gi RAM)
# 4. Streams binaries into the Pod, runs benchmarks across iterations,
#    and retrieves benchmark logs, binary pprof profiles, and readable text profiles
# 5. Cleans up Pod reliably on exit (trap EXIT)
# 6. Generates <RESULTS_DIR>/summary.json containing composite & per-op metrics
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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$RESULTS_DIR" != /* ]]; then
  RESULTS_DIR="${SCRIPT_DIR}/${RESULTS_DIR}"
fi

mkdir -p "${RESULTS_DIR}/monitor" "${RESULTS_DIR}/profiles"
echo $$ > "${RESULTS_DIR}/monitor/benchmark.pid"

# Source environment
if [ -f "${SCRIPT_DIR}/set-env.sh" ]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/set-env.sh"
fi

# Ensure binaries exist
BIN_DIR="${RESULTS_DIR}/bin"
if [ ! -f "${BIN_DIR}/ch.test" ] || [ ! -f "${BIN_DIR}/ategcs.test" ] || [ ! -f "${BIN_DIR}/tarutil.test" ]; then
  echo "Binaries not found in ${BIN_DIR}, invoking build.sh..."
  "${SCRIPT_DIR}/build.sh" "${RESULTS_DIR}"
fi

# Unique run identifier for parallel execution safety
RUN_ID="${RUN_ID:-$(date +%s)-$RANDOM}"
POD_NAME="bench-runner-${RUN_ID}"
NAMESPACE="${NAMESPACE:-microbench}"

echo "Starting Substrate Go Microbenchmark execution in Pod ${POD_NAME} (${BENCHMARK_ITERATIONS} iterations)..."

# Ensure cleanup on exit
cleanup_pod() {
  echo "Cleaning up Pod ${NAMESPACE}/${POD_NAME}..."
  kubectl delete pod "${POD_NAME}" -n "${NAMESPACE}" --wait=false 2>/dev/null || true
}
trap cleanup_pod EXIT

# Launch Guaranteed QoS Pod on the c3 node pool
echo "Creating runner Pod ${POD_NAME} on c3 node pool (Guaranteed QoS: 4 CPU, 8Gi RAM)..."
cat <<POD_EOF | kubectl apply -n "${NAMESPACE}" -f -
apiVersion: v1
kind: Pod
metadata:
  name: ${POD_NAME}
  namespace: ${NAMESPACE}
  labels:
    app: microbench-runner
    run-id: "${RUN_ID}"
spec:
  restartPolicy: Never
  nodeSelector:
    cloud.google.com/gke-nodepool: substrate-bench-pool
  containers:
  - name: runner
    image: alpine:latest
    command: ["sh", "-c", "mkdir -p /bench && trap : TERM INT; sleep 3600 & wait"]
    resources:
      requests:
        cpu: "4"
        memory: "8Gi"
      limits:
        cpu: "4"
        memory: "8Gi"
POD_EOF

# Wait for Pod to be ready
echo "Waiting for Pod ${POD_NAME} to be ready..."
kubectl wait --for=condition=Ready "pod/${POD_NAME}" -n "${NAMESPACE}" --timeout=60s

# Copy binaries into the Pod
echo "Copying test binaries into Pod..."
kubectl cp "${BIN_DIR}/ch.test" "${NAMESPACE}/${POD_NAME}:/bench/ch.test"
kubectl cp "${BIN_DIR}/ategcs.test" "${NAMESPACE}/${POD_NAME}:/bench/ategcs.test"
kubectl cp "${BIN_DIR}/tarutil.test" "${NAMESPACE}/${POD_NAME}:/bench/tarutil.test"

kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- chmod +x /bench/ch.test /bench/ategcs.test /bench/tarutil.test

# Packages & benchmarks to run
BENCH_SPECS=(
  "ch:${BIN_DIR}/ch.test:/bench/ch.test:BenchmarkMergeDeltaIntoBase|BenchmarkCopySparseRegions"
  "ategcs:${BIN_DIR}/ategcs.test:/bench/ategcs.test:BenchmarkWriteSparseZstd|BenchmarkReadSparseZstd"
  "tarutil:${BIN_DIR}/tarutil.test:/bench/tarutil.test:BenchmarkExtract|BenchmarkCreate"
)

for ((i=1; i<=BENCHMARK_ITERATIONS; i++)); do
  ITER_DIR="${RESULTS_DIR}/iter_${i}"
  ITER_PROFILES="${ITER_DIR}/profiles"
  mkdir -p "${ITER_DIR}" "${ITER_PROFILES}"

  echo ">>> [Iteration ${i}/${BENCHMARK_ITERATIONS}] Running benchmarks inside Pod..."
  LOG_FILE="${ITER_DIR}/bench.log"
  : > "${LOG_FILE}"

  for spec in "${BENCH_SPECS[@]}"; do
    IFS=":" read -r name local_bin pod_bin pattern <<< "${spec}"
    POD_CPU="/bench/cpu_${name}_iter${i}.pprof"
    POD_MEM="/bench/mem_${name}_iter${i}.pprof"
    LOCAL_CPU="${ITER_PROFILES}/cpu_${name}.pprof"
    LOCAL_MEM="${ITER_PROFILES}/mem_${name}.pprof"
    TXT_CPU="${ITER_PROFILES}/cpu_${name}.txt"
    TXT_MEM="${ITER_PROFILES}/mem_${name}.txt"

    kubectl exec -n "${NAMESPACE}" "${POD_NAME}" -- \
      "${pod_bin}" \
        -test.bench="${pattern}" \
        -test.benchtime=5x \
        -test.benchmem \
        -test.cpuprofile="${POD_CPU}" \
        -test.memprofile="${POD_MEM}" \
        -test.run=^$ >> "${LOG_FILE}" 2>&1 || {
          echo "Error in iteration ${i} (${name}): Benchmark execution failed in Pod" >&2
          cat "${LOG_FILE}" >&2
          python3 "${SCRIPT_DIR}/parse_benchmark.py" "${LOG_FILE}" "${ITER_DIR}" 2>/dev/null || true
          exit 1
        }

    # Retrieve binary profiles from Pod
    kubectl cp "${NAMESPACE}/${POD_NAME}:${POD_CPU}" "${LOCAL_CPU}" 2>/dev/null || true
    kubectl cp "${NAMESPACE}/${POD_NAME}:${POD_MEM}" "${LOCAL_MEM}" 2>/dev/null || true

    # Generate version-controllable plain text profile summaries
    if [ -f "${LOCAL_CPU}" ]; then
      go tool pprof -top -nodecount=30 "${local_bin}" "${LOCAL_CPU}" > "${TXT_CPU}" 2>/dev/null || true
    fi
    if [ -f "${LOCAL_MEM}" ]; then
      go tool pprof -top -nodecount=30 "${local_bin}" "${LOCAL_MEM}" > "${TXT_MEM}" 2>/dev/null || true
    fi
  done

  # Parse iteration metrics
  python3 "${SCRIPT_DIR}/parse_benchmark.py" "${LOG_FILE}" "${ITER_DIR}"
done

# Aggregate iterations using median composite_ns_per_op
python3 - << 'PYEOF' "$RESULTS_DIR" "$BENCHMARK_ITERATIONS"
import sys
import os
import json
import shutil

results_dir = sys.argv[1]
iterations = int(sys.argv[2])

iter_summaries = []
for i in range(1, iterations + 1):
    iter_file = os.path.join(results_dir, f"iter_{i}", "summary.json")
    if os.path.exists(iter_file):
        try:
            with open(iter_file, "r") as f:
                data = json.load(f)
                if data.get("metrics", {}).get("composite_ns_per_op", 0.0) > 0:
                    iter_summaries.append((i, data))
        except Exception as e:
            print(f"Warning: Could not read {iter_file}: {e}")

if not iter_summaries:
    print("Error: No valid iteration summaries found to aggregate.")
    with open(os.path.join(results_dir, "error.json"), "w") as f:
        json.dump({"error": "No valid iteration summaries found", "stage": "aggregation"}, f, indent=2)
    sys.exit(1)

# Sort iterations by primary objective (composite_ns_per_op ascending)
iter_summaries.sort(key=lambda item: item[1].get("metrics", {}).get("composite_ns_per_op", float("inf")))
median_idx, median_summary = iter_summaries[len(iter_summaries) // 2]
print(f"Selected median iteration: iter_{median_idx}")

median_iter_dir = os.path.join(results_dir, f"iter_{median_idx}")
for fname in ["bench.log"]:
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
    "benchmarks": median_summary.get("benchmarks", {}),
    "profiling_summary": median_summary.get("profiling_summary", {}),
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
PYEOF

echo "Benchmark execution finished successfully."
