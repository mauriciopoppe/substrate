#!/usr/bin/env bash
# ==============================================================================
# Build / verification script for pure Go microbenchmark trials.
# Runs unit tests to ensure code mutations compile and pass correctness checks
# before running the benchmark suite.
# ==============================================================================

set -euo pipefail

RESULTS_DIR="${1:-results/scratch}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ensure absolute path for RESULTS_DIR
if [[ "$RESULTS_DIR" != /* ]]; then
  RESULTS_DIR="${SCRIPT_DIR}/${RESULTS_DIR}"
fi
mkdir -p "${RESULTS_DIR}"

SUBSTRATE_DIR="${SCRIPT_DIR}/substrate"

echo ">>> Verifying Go compilation and unit tests across mutated packages..."

cd "${SUBSTRATE_DIR}"

# Run unit tests across the target packages
go test -v -run 'TestMerge|TestSparseZstd|TestRoundTrip' \
  ./cmd/ateom-microvm/internal/ch \
  ./cmd/atelet/internal/ategcs \
  ./internal/tarutil > "${RESULTS_DIR}/build_test.log" 2>&1

echo ">>> Build and unit test verification succeeded."
echo "BUILD_STATUS=SUCCESS" > "${RESULTS_DIR}/build_artifacts.env"
