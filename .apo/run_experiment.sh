#!/bin/bash
# ==============================================================================
# APO Benchmark Execution Script Wrapper
# Delegates execution to .apo/run_experiment.py
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

# Source environment if present
if [ -f "${SCRIPT_DIR}/set-env.sh" ]; then
  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/set-env.sh"
fi

exec python3 "${SCRIPT_DIR}/run_experiment.py" "$@"
