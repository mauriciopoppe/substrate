#!/usr/bin/env bash
# ==============================================================================
# Build script for pure Go microbenchmark binaries.
# Compiles statically linked Linux/amd64 test binaries ready to ship to GKE Pods.
# ==============================================================================

set -euo pipefail

export GOFLAGS="${GOFLAGS:--mod=mod}"

RESULTS_DIR="${1:-.apo/results/scratch}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKLOAD_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "$RESULTS_DIR" != /* ]]; then
  RESULTS_DIR="${WORKLOAD_ROOT}/${RESULTS_DIR}"
fi
mkdir -p "${RESULTS_DIR}"

BIN_DIR="${RESULTS_DIR}/bin"
mkdir -p "${BIN_DIR}"

cd "${WORKLOAD_ROOT}"

echo ">>> Verifying and compiling standalone Linux amd64 test binaries..."

# 1. Compile ch test binary
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go test -c -o "${BIN_DIR}/ch.test" ./cmd/ateom-microvm/internal/ch

# 2. Compile ategcs test binary
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go test -c -o "${BIN_DIR}/ategcs.test" ./cmd/atelet/internal/ategcs

# 3. Compile tarutil test binary
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go test -c -o "${BIN_DIR}/tarutil.test" ./internal/tarutil

chmod +x "${BIN_DIR}/"*.test

echo ">>> Successfully built benchmark binaries in ${BIN_DIR}:"
ls -lh "${BIN_DIR}/"*.test

echo "BUILD_STATUS=SUCCESS" > "${RESULTS_DIR}/build_artifacts.env"
echo "BIN_DIR=${BIN_DIR}" >> "${RESULTS_DIR}/build_artifacts.env"
