#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

log "Stopping all services"

PROCS_FILE="${REPO_ROOT}/.nightcraft-logs/processes.txt"
if [[ -f "${PROCS_FILE}" ]]; then
  while IFS=: read -r pid name; do
    [[ -z "${pid}" ]] && continue
    if kill -0 "${pid}" 2>/dev/null; then
      kill "${pid}" 2>/dev/null || true
      log "  stopped ${name} (PID ${pid})"
    fi
  done < "${PROCS_FILE}"
  rm -f "${PROCS_FILE}"
else
  log "No processes file found, scanning for orphaned .pid files"
fi

killed_orphans=0
for pid_file in "${SHARED_DIR}"/*.pid; do
  [[ -f "${pid_file}" ]] || continue
  pid=$(cat "${pid_file}" 2>/dev/null || echo "")
  [[ -z "${pid}" ]] && { rm -f "${pid_file}"; continue; }
  if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    killed_orphans=$((killed_orphans + 1))
  fi
  rm -f "${pid_file}"
done

if [[ "${killed_orphans}" -gt 0 ]]; then
  log "  ${killed_orphans} orphaned processes stopped"
fi

# Final sweep: kill anything still bound to a service port. This catches
# Flask reloader worker children that outlive their parent process.
SERVICE_PORTS=(5100 5333 5400 5500 5600 5000 5800 5900 8000)
for p in "${SERVICE_PORTS[@]}"; do
  _ppid=$(ss -tlnp "sport = :${p}" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
  if [[ -n "${_ppid}" ]]; then
    kill "${_ppid}" 2>/dev/null || true
    log "  freed port ${p} (PID ${_ppid})"
  fi
done

log "All services stopped"