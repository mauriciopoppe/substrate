#!/bin/bash
# ==============================================================================
# APO Environment Configuration for Substrate Workload (GKE isolated)
# ==============================================================================

# Base Runtime Environment Module
export SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

# Ensure we can find packages installed in real user home
REAL_USER=$(whoami)
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
export PYTHONPATH="/usr/local/google/home/${REAL_USER}/.local/lib/python${PYTHON_VERSION}/site-packages:${PYTHONPATH}"

# When running inside ephemeral git worktrees, discover parent repo root and symlink .venv
GIT_COMMON_DIR=$(git rev-parse --git-common-dir 2>/dev/null || true)
if [ -n "$GIT_COMMON_DIR" ] && [ "$GIT_COMMON_DIR" != ".git" ]; then
  PARENT_REPO_ROOT=$(cd "$GIT_COMMON_DIR/.." && pwd)
  if [ -d "${PARENT_REPO_ROOT}/.apo/.venv" ] && [ ! -d "${SCRIPT_DIR}/.venv" ]; then
    ln -s "${PARENT_REPO_ROOT}/.apo/.venv" "${SCRIPT_DIR}/.venv"
  fi
fi

# Initialize and activate Python virtual environment
if [ -f "${SCRIPT_DIR}/.venv/bin/activate" ]; then
  source "${SCRIPT_DIR}/.venv/bin/activate"
else
  echo "Initializing Python virtual environment..."
  python3 -m venv "${SCRIPT_DIR}/.venv"
  touch "${SCRIPT_DIR}/.venv/DONT_FOLLOW_SYMLINKS_WHEN_TRAVERSING_THIS_DIRECTORY_VIA_A_RECURSIVE_TARGET_PATTERN"
  touch "${SCRIPT_DIR}/.venv/bin/DONT_FOLLOW_SYMLINKS_WHEN_TRAVERSING_THIS_DIRECTORY_VIA_A_RECURSIVE_TARGET_PATTERN"
  source "${SCRIPT_DIR}/.venv/bin/activate"
  python3 -m pip install optuna pyyaml --quiet -i https://pypi.org/simple
fi

# Source hardware stack parameters staged by the orchestrator in the worktree
if [ -f "${SCRIPT_DIR}/stack.env" ]; then
  source "${SCRIPT_DIR}/stack.env"
fi

# Isolate scratch directory to workspace
export SCRATCH_DIR="${SCRIPT_DIR}/scratch"
mkdir -p "${SCRATCH_DIR}"

# GKE Isolated Configuration Module
# Capture currently active global account before isolation
ACTIVE_ACCOUNT=$(gcloud config get-value account 2>/dev/null || true)

# Isolate gcloud configuration to workspace directory
export CLOUDSDK_CONFIG="${SCRIPT_DIR}/.gcloud-config"
mkdir -p "${CLOUDSDK_CONFIG}"

# Copy default credentials if they exist and haven't been copied yet
ADC_SOURCE="${HOME}/.config/gcloud/application_default_credentials.json"
ADC_DEST="${CLOUDSDK_CONFIG}/application_default_credentials.json"
if [ -f "$ADC_SOURCE" ] && [ ! -f "$ADC_DEST" ]; then
  cp "$ADC_SOURCE" "$ADC_DEST"
  gcloud config set auth/credential_file_override "$ADC_DEST" 2>/dev/null || true
fi

# Copy user credentials if they exist and haven't been copied yet to fix GKE 403
CREDS_SOURCE="${HOME}/.config/gcloud/credentials.db"
CREDS_DEST="${CLOUDSDK_CONFIG}/credentials.db"
if [ -f "$CREDS_SOURCE" ] && [ ! -f "$CREDS_DEST" ]; then
  cp "$CREDS_SOURCE" "$CREDS_DEST"
fi

# Isolate kubectl configuration to workspace directory
export KUBECONFIG="${SCRIPT_DIR}/.kubeconfig"

# Target Project & Cluster
export PROJECT_ID="${PROJECT_ID:-mauriciopoppe-gke-dev}"
export CLUSTER_NAME="${CLUSTER_NAME:-substrate-test-2}"
export COMPUTE_REGION="${COMPUTE_REGION:-us-west1}"
export COMPUTE_ZONE="${COMPUTE_ZONE:-us-west1-c}"
export NAMESPACE="${NAMESPACE:-benchmarking}"
export BUCKET_NAME="${BUCKET_NAME:-ate-snapshots-mauriciopoppe-gke-dev-us-west1-c}"
export KO_DOCKER_REPO="${KO_DOCKER_REPO:-gcr.io/${PROJECT_ID}/ate-images}"
export KO_DEFAULTPLATFORMS="${KO_DEFAULTPLATFORMS:-linux/amd64}"

# Ensure the correct project, zone/region, and account are set in isolated config
gcloud config set project "${PROJECT_ID}" 2>/dev/null || true
if [ -n "${COMPUTE_ZONE:-}" ]; then
  gcloud config set compute/zone "${COMPUTE_ZONE}" 2>/dev/null || true
fi
if [ -n "${COMPUTE_REGION:-}" ]; then
  gcloud config set compute/region "${COMPUTE_REGION}" 2>/dev/null || true
fi
if [ -n "$ACTIVE_ACCOUNT" ]; then
  gcloud config set account "${ACTIVE_ACCOUNT}" 2>/dev/null || true
fi

# Determine zone vs. region flag for get-credentials
LOCATION_FLAG=""
if [ -n "${COMPUTE_ZONE:-}" ]; then
  LOCATION_FLAG="--zone=${COMPUTE_ZONE}"
elif [ -n "${COMPUTE_REGION:-}" ]; then
  LOCATION_FLAG="--region=${COMPUTE_REGION}"
fi

# Ensure cluster credentials exist in isolated KUBECONFIG (do not overwrite if present)
if ! kubectl config get-contexts "gke_${PROJECT_ID}_${COMPUTE_REGION}_${CLUSTER_NAME}" &>/dev/null && \
   ! kubectl config get-contexts "gke_${PROJECT_ID}_${COMPUTE_ZONE}_${CLUSTER_NAME}" &>/dev/null && \
   ! kubectl config get-contexts "${CLUSTER_NAME}" &>/dev/null; then
  if [ -n "${CLUSTER_NAME:-}" ] && command -v gcloud &>/dev/null && [ -n "${LOCATION_FLAG}" ]; then
    gcloud container clusters get-credentials "${CLUSTER_NAME}" ${LOCATION_FLAG} --project="${PROJECT_ID}" 2>/dev/null || true
  fi
fi

# GCE VM SSH Debugging Helper Module
mine:gce_ssh() {
  local vm=$1
  shift
  gcloud compute ssh "$vm" --zone="${COMPUTE_ZONE}" "$@" -- -o "Hostname=nic0.${vm}.${COMPUTE_ZONE}.c.${PROJECT_ID}.internal.gcpnode.com"
}

# Container Registry Authentication Module
if command -v gcloud &>/dev/null; then
  REGISTRY_ENDPOINT="gcr.io"
  if [ -n "${COMPUTE_REGION:-}" ]; then
    REGISTRY_ENDPOINT="${COMPUTE_REGION}-docker.pkg.dev,gcr.io"
  fi
  gcloud auth configure-docker "${REGISTRY_ENDPOINT}" --quiet 2>/dev/null || true
fi
