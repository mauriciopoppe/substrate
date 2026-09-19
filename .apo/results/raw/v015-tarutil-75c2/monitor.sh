#!/bin/bash
RESULTS_DIR="${1:-.}"
PID="${2:-}"
INTERVAL="${3:-5}"
MAX_ITERATIONS="${4:-0}"
iteration=0

mkdir -p "${RESULTS_DIR}/monitor"
echo $$ > "${RESULTS_DIR}/monitor/monitor.pid"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Telemetry monitor started for PID=${PID} (monitor_pid=$$)" >> "${RESULTS_DIR}/monitor/monitor_events.log"

while true; do
if [ -n "${PID}" ] && ! kill -0 "${PID}" 2>/dev/null; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Monitored process PID=${PID} exited. Stopping telemetry monitor." >> "${RESULTS_DIR}/monitor/monitor_events.log"
  break
fi
if [ "${MAX_ITERATIONS}" -gt 0 ] && [ "${iteration}" -ge "${MAX_ITERATIONS}" ]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Max iterations (${MAX_ITERATIONS}) reached. Stopping telemetry monitor." >> "${RESULTS_DIR}/monitor/monitor_events.log"
  break
fi
for trait_script in "${RESULTS_DIR}/monitor_traits"/*.sh; do
  if [ -f "${trait_script}" ]; then
    RESULTS_DIR="${RESULTS_DIR}" bash "${trait_script}" 2>/dev/null || true
  fi
done
iteration=$((iteration + 1))
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Telemetry heartbeat (iteration=${iteration}, PID=${PID} active)" >> "${RESULTS_DIR}/monitor/monitor_events.log"
sleep "${INTERVAL}"
done
