#!/usr/bin/env bash
# Copyright 2026 Google LLC
# Build script for Substrate Micro-VM container images during APO trials.
# Produces: <RESULTS_DIR>/build_artifacts.env containing ATEOM_MICROVM_IMAGE and ATELET_IMAGE

set -euo pipefail

RESULTS_DIR="${1:-/tmp/results}"
mkdir -p "${RESULTS_DIR}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/set-env.sh"

SUBSTRATE_DIR="${SCRIPT_DIR}/substrate"

# Source substrate environment if present
if [ -f "${SUBSTRATE_DIR}/.ate-dev-env.sh" ]; then
  # shellcheck disable=SC1091
  source "${SUBSTRATE_DIR}/.ate-dev-env.sh"
fi

# Generate deterministic trial tag
TRIAL_ID="${TRIAL_ID:-$(date +%s)}"
IMAGE_TAG="apo-trial-${TRIAL_ID}"

echo ">>> Building ateom-microvm and atelet container images from ${SUBSTRATE_DIR}..."

KO_DOCKER_REPO="${KO_DOCKER_REPO:-gcr.io/${PROJECT_ID:-mauriciopoppe-gke-dev}/ate-images}"
export KO_DOCKER_REPO
export KO_DEFAULTPLATFORMS="${KO_DEFAULTPLATFORMS:-linux/amd64}"

ATEOM_MICROVM_IMAGE="$(cd "${SUBSTRATE_DIR}" && ./hack/run-tool.sh ko build --platform=linux/amd64 --tags="${IMAGE_TAG}" ./cmd/ateom-microvm)"
ATELET_IMAGE="$(cd "${SUBSTRATE_DIR}" && ./hack/run-tool.sh ko build --platform=linux/amd64 --tags="${IMAGE_TAG}" ./cmd/atelet)"

cat <<EOF > "${RESULTS_DIR}/build_artifacts.env"
ATEOM_MICROVM_IMAGE=${ATEOM_MICROVM_IMAGE}
ATELET_IMAGE=${ATELET_IMAGE}
EOF

echo ">>> Built and pushed images:"
echo "    ATEOM_MICROVM_IMAGE=${ATEOM_MICROVM_IMAGE}"
echo "    ATELET_IMAGE=${ATELET_IMAGE}"

