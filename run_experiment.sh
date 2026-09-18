#!/usr/bin/env bash
# ==============================================================================
# WorkQueue Benchmark Execution Script for Pure Go Microbenchmark Suite
# Conforms to the APO Benchmark Execution Contract:
# 1. Accepts $1 as <RESULTS_DIR>, supports --iterations / -n (default: 3)
# 2. Writes shell PID $! to <RESULTS_DIR>/monitor/benchmark.pid
# 3. Streams stdout/stderr to <RESULTS_DIR>/benchmark_output.log
# 4. Executes `go test -bench` across core hotpaths
# 5. Generates <RESULTS_DIR>/summary.json containing composite & per-op metrics
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

SUBSTRATE_DIR="${SCRIPT_DIR}/substrate"
cd "${SUBSTRATE_DIR}"

# Source tunables if present
if [ -f "${SCRIPT_DIR}/manifests/tunables.env" ]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/manifests/tunables.env"
fi

echo "Starting Substrate Go Microbenchmark execution in ${SUBSTRATE_DIR} (${BENCHMARK_ITERATIONS} iterations)..."

# Packages to benchmark
PACKAGES=(
  "ch:./cmd/ateom-microvm/internal/ch:BenchmarkMergeDeltaIntoBase|BenchmarkCopySparseRegions"
  "ategcs:./cmd/atelet/internal/ategcs:BenchmarkWriteSparseZstd|BenchmarkReadSparseZstd"
  "tarutil:./internal/tarutil:BenchmarkExtract|BenchmarkCreate"
)

for ((i=1; i<=BENCHMARK_ITERATIONS; i++)); do
  ITER_DIR="${RESULTS_DIR}/iter_${i}"
  ITER_PROFILES="${ITER_DIR}/profiles"
  mkdir -p "${ITER_DIR}" "${ITER_PROFILES}"

  echo ">>> [Iteration ${i}/${BENCHMARK_ITERATIONS}] Running benchmarks..."
  LOG_FILE="${ITER_DIR}/bench.log"
  : > "${LOG_FILE}"

  for pkg_spec in "${PACKAGES[@]}"; do
    IFS=":" read -r name path pattern <<< "${pkg_spec}"
    PKG_CPU="${ITER_PROFILES}/cpu_${name}.pprof"
    PKG_MEM="${ITER_PROFILES}/mem_${name}.pprof"

    go test -bench="${pattern}" \
      -benchtime=5x \
      -benchmem \
      -cpuprofile="${PKG_CPU}" \
      -memprofile="${PKG_MEM}" \
      -run=^$ \
      "${path}" >> "${LOG_FILE}" 2>&1 || {
        echo "Error in iteration ${i} (${name}): Benchmark execution failed" >&2
        cat "${LOG_FILE}" >&2
        python3 "${SCRIPT_DIR}/parse_benchmark.py" "${LOG_FILE}" "${ITER_DIR}" 2>/dev/null || true
        exit 1
      }
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
