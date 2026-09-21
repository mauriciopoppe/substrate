#!/usr/bin/env bash
# ==============================================================================
# Build script for Substrate container images during APO trials.
# Produces: <RESULTS_DIR>/build_artifacts.env containing ATELET_IMAGE (and optionally ATEOM_MICROVM_IMAGE)
# ==============================================================================

set -euo pipefail

RESULTS_DIR="${1:-/tmp/results}"
mkdir -p "${RESULTS_DIR}"

APO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SUBSTRATE_DIR="$(cd "${APO_DIR}/.." && pwd)"

# shellcheck disable=SC1091
source "${APO_DIR}/set-env.sh"

# Source substrate environment if present
if [ -f "${SUBSTRATE_DIR}/.ate-dev-env.sh" ]; then
  # shellcheck disable=SC1091
  source "${SUBSTRATE_DIR}/.ate-dev-env.sh"
fi

# Generate deterministic trial tag
TRIAL_ID="${TRIAL_ID:-$(date +%s)}"
IMAGE_TAG="apo-trial-${TRIAL_ID}"

echo ">>> Building container images from ${SUBSTRATE_DIR}..."

KO_DOCKER_REPO="${KO_DOCKER_REPO:-gcr.io/${PROJECT_ID:-mauriciopoppe-gke-dev}/ate-images}"
export KO_DOCKER_REPO
export KO_DEFAULTPLATFORMS="${KO_DEFAULTPLATFORMS:-linux/amd64}"

ATELET_IMAGE="$(cd "${SUBSTRATE_DIR}" && ./hack/run-tool.sh ko build --platform=linux/amd64 --tags="${IMAGE_TAG}" ./cmd/atelet)"

cat <<EOF > "${RESULTS_DIR}/build_artifacts.env"
ATELET_IMAGE=${ATELET_IMAGE}
EOF

echo ">>> Built and pushed images:"
echo "    ATELET_IMAGE=${ATELET_IMAGE}"
