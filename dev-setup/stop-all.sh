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

log "All services stopped"