#!/usr/bin/env bash
# ==============================================================================
# Build script for Substrate container images during APO trials.
# Produces: <RESULTS_DIR>/build_artifacts.env containing:
#   - ATELET_IMAGE (cmd/atelet)
#   - ATENET_IMAGE (cmd/atenet / atenet-router)
#   - RUNNER_IMAGE (benchmarking/locust)
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
PROJECT_ID="${PROJECT_ID:-mauriciopoppe-gke-dev}"

echo ">>> Substrate container build pipeline (trial tag: ${IMAGE_TAG})..."

KO_DOCKER_REPO="${KO_DOCKER_REPO:-gcr.io/${PROJECT_ID}/ate-images}"
export KO_DOCKER_REPO
export KO_DEFAULTPLATFORMS="${KO_DEFAULTPLATFORMS:-linux/amd64}"

has_changes() {
  local pattern="$1"
  if [ "${FORCE_BUILD:-false}" = "true" ]; then
    return 0
  fi
  # Check unstaged or staged working tree
  if git status -s -- "${SUBSTRATE_DIR}/${pattern}" 2>/dev/null | grep -q .; then
    return 0
  fi
  # Check HEAD commit if present
  if git rev-parse --verify HEAD~1 &>/dev/null; then
    if git diff --name-only HEAD~1 HEAD -- "${SUBSTRATE_DIR}/${pattern}" 2>/dev/null | grep -q .; then
      return 0
    fi
  fi
  return 1
}

BUILD_ATELET=false
BUILD_ATENET=false
BUILD_RUNNER=false

if [ "${FORCE_BUILD:-false}" = "true" ] || [ "${BUILD_ALL:-false}" = "true" ]; then
  BUILD_ATELET=true
  BUILD_ATENET=true
  BUILD_RUNNER=true
else
  if has_changes "cmd/atelet" || has_changes "internal/atelet"; then
    BUILD_ATELET=true
  fi
  if has_changes "cmd/atenet" || has_changes "internal/atenet"; then
    BUILD_ATENET=true
  fi
  if has_changes "benchmarking" || has_changes "internal/benchmarking"; then
    BUILD_RUNNER=true
  fi
  # If none explicitly changed (clean working tree or initial build), build all so artifacts exist
  if [ "$BUILD_ATELET" = "false" ] && [ "$BUILD_ATENET" = "false" ] && [ "$BUILD_RUNNER" = "false" ]; then
    echo ">>> No specific component changes detected; building all components."
    BUILD_ATELET=true
    BUILD_ATENET=true
    BUILD_RUNNER=true
  fi
fi

# Initialize build artifacts file
true > "${RESULTS_DIR}/build_artifacts.env"

if [ "$BUILD_ATELET" = "true" ]; then
  echo ">>> Building atelet daemonset image (${IMAGE_TAG})..."
  ATELET_IMAGE="$(cd "${SUBSTRATE_DIR}" && ./hack/run-tool.sh ko build --platform=linux/amd64 --tags="${IMAGE_TAG}" ./cmd/atelet)"
  echo "ATELET_IMAGE=${ATELET_IMAGE}" >> "${RESULTS_DIR}/build_artifacts.env"
  echo "    ATELET_IMAGE=${ATELET_IMAGE}"
fi

if [ "$BUILD_ATENET" = "true" ]; then
  echo ">>> Building atenet-router image (${IMAGE_TAG})..."
  ATENET_IMAGE="$(cd "${SUBSTRATE_DIR}" && ./hack/run-tool.sh ko build --platform=linux/amd64 --tags="${IMAGE_TAG}" ./cmd/atenet)"
  echo "ATENET_IMAGE=${ATENET_IMAGE}" >> "${RESULTS_DIR}/build_artifacts.env"
  echo "    ATENET_IMAGE=${ATENET_IMAGE}"
fi

if [ "$BUILD_RUNNER" = "true" ]; then
  echo ">>> Building runner (locust-test) image (${IMAGE_TAG})..."
  RUNNER_IMAGE="us-docker.pkg.dev/${PROJECT_ID}/gcr.io/ate-images/locust-test:${IMAGE_TAG}"
  LATEST_RUNNER_IMAGE="us-docker.pkg.dev/${PROJECT_ID}/gcr.io/ate-images/locust-test:latest"
  docker build --platform linux/amd64 -t "${RUNNER_IMAGE}" -t "${LATEST_RUNNER_IMAGE}" -f "${SUBSTRATE_DIR}/benchmarking/locust/Dockerfile" "${SUBSTRATE_DIR}"
  docker push "${RUNNER_IMAGE}"
  docker push "${LATEST_RUNNER_IMAGE}"
  echo "RUNNER_IMAGE=${RUNNER_IMAGE}" >> "${RESULTS_DIR}/build_artifacts.env"
  echo "    RUNNER_IMAGE=${RUNNER_IMAGE}"
fi

echo ">>> Build completed. Artifacts written to ${RESULTS_DIR}/build_artifacts.env"
