#!/usr/bin/env bash
# Copyright 2026 Google LLC
# Build script for Substrate Ingress Router container images during APO trials.
# Produces: <RESULTS_DIR>/build_artifacts.env containing ROUTER_IMAGE=<image_uri>

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

echo ">>> Building atenet-router container image from ${SUBSTRATE_DIR}..."

KO_DOCKER_REPO="${KO_DOCKER_REPO:-gcr.io/${PROJECT_ID:-mauriciopoppe-gke-dev}/ate-images}"
export KO_DOCKER_REPO
export KO_DEFAULTPLATFORMS="${KO_DEFAULTPLATFORMS:-linux/amd64}"

ROUTER_IMAGE="$(cd "${SUBSTRATE_DIR}" && ./hack/run-tool.sh ko build --platform=linux/amd64 --tags="${IMAGE_TAG}" ./cmd/atenet)"
echo "ROUTER_IMAGE=${ROUTER_IMAGE}" > "${RESULTS_DIR}/build_artifacts.env"
echo ">>> Built and pushed image: ${ROUTER_IMAGE}"
