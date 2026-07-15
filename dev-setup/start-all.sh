#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

log "Starting all services in background"

ensure_dir "${RADIO_SHARED}/instance"
ensure_dir "${AUTH_SHARED}/keys"
ensure_dir "${NEERA_SHARED}/instance/uploads/works"
ensure_dir "${SHARED_DIR}/app-game"

mkdir -p "$(dirname "${LOG_DIR}")"
PROCS_FILE="${REPO_ROOT}/.nightcraft-logs/processes.txt"
: > "${PROCS_FILE}"

port_in_use() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -tln "sport = :${port}" 2>/dev/null | grep -q ":${port}[[:space:]]"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -i :"${port}" >/dev/null 2>&1
  else
    (echo > "/dev/tcp/127.0.0.1/${port}") 2>/dev/null
  fi
}

# Launch a service in an isolated subshell. We clear every inherited EXPORTED
# variable first, then source only this service's own env file. This prevents
# one service from inheriting another's variables (e.g. DATABASE_URL leaking
# from an earlier service into a later one).
start_service() {
  local name="$1"
  local env_name="$2"
  local src_dir="$3"
  local venv="$4"
  local port="${5:-}"
  local pid_file="${SHARED_DIR}/${name}.pid"
  local log_file="${LOG_DIR}/${name}.log"
  local env_file="${ENV_DIR}/${env_name}.env"

  if [[ -f "${pid_file}" ]]; then
    local old_pid
    old_pid=$(cat "${pid_file}" 2>/dev/null || echo "")
    if [[ -n "${old_pid}" ]] && kill -0 "${old_pid}" 2>/dev/null; then
      log "  ${name} already running (PID ${old_pid}), skipping"
      echo "${old_pid}:${name}" >> "${PROCS_FILE}"
      return
    fi
    rm -f "${pid_file}"
  fi

  if [[ -n "${port}" ]] && port_in_use "${port}"; then
    log "  port ${port} already in use — ${name} may already be running externally"
  fi

  (
    _nc_path="$PATH" _nc_home="$HOME" _nc_term="${TERM:-}" _nc_lang="${LANG:-}" _nc_lc="${LC_ALL:-}"
    local _nc_vars
    _nc_vars=$(compgen -e)
    [[ -n "${_nc_vars}" ]] && unset -v ${_nc_vars}
    PATH="$_nc_path" HOME="$_nc_home" TERM="$_nc_term" LANG="$_nc_lang" LC_ALL="$_nc_lc"
    set -a
    [[ -f "${env_file}" ]] && source "${env_file}"
    set +a
    export NIGHTCRAFT_SHARED_DIR="${SHARED_DIR}"
    export NIGHTCRAFT_ENV_DIR="${ENV_DIR}"
    cd "${src_dir}"
    exec "${venv}/bin/python" run.py
  ) > "${log_file}" 2>&1 &
  local pid=$!
  echo "${pid}" > "${pid_file}"
  echo "${pid}:${name}" >> "${PROCS_FILE}"
  log "  ${name} started (PID ${pid}, log: ${log_file##*/})"
}

start_service "auth"    "service-auth"  "${AUTH_SRC_DIR}"              "${AUTH_VENV}"  5100
sleep 2

start_service "radio"   "app-radio"     "${RADIO_SRC_DIR}"             "${RADIO_VENV}"  5333
start_service "neera"   "app-neera"     "${NEERA_SRC_DIR}"             "${NEERA_VENV}"  5600
start_service "landing" "app-landing"   "${LANDING_SRC_DIR}"           "${LANDING_VENV}" 5400
start_service "admin"   "app-admin"     "${ADMIN_SRC_DIR}"             "${ADMIN_VENV}"  5500
start_service "game"    "app-game"      "${GAME_SRC_DIR}"              "${GAME_VENV}"   5800
start_service "note"    "app-note"      "${NOTE_SRC_DIR}"              "${NOTE_VENV}"   5900

log "  mindmap (FastAPI)..."
MINDMAP_PID=""
if [[ -f "${SHARED_DIR}/mindmap.pid" ]]; then
  MINDMAP_PID=$(cat "${SHARED_DIR}/mindmap.pid" 2>/dev/null || echo "")
  if [[ -n "${MINDMAP_PID}" ]] && kill -0 "${MINDMAP_PID}" 2>/dev/null; then
    log "  mindmap already running (PID ${MINDMAP_PID}), skipping"
    echo "${MINDMAP_PID}:mindmap" >> "${PROCS_FILE}"
  else
    MINDMAP_PID=""
    rm -f "${SHARED_DIR}/mindmap.pid"
  fi
fi
if [[ -z "${MINDMAP_PID}" ]]; then
  (
    _nc_path="$PATH" _nc_home="$HOME" _nc_term="${TERM:-}" _nc_lang="${LANG:-}" _nc_lc="${LC_ALL:-}"
    _nc_vars=$(compgen -e)
    [[ -n "${_nc_vars}" ]] && unset -v ${_nc_vars}
    PATH="$_nc_path" HOME="$_nc_home" TERM="$_nc_term" LANG="$_nc_lang" LC_ALL="$_nc_lc"
    export NIGHTCRAFT_SHARED_DIR="${SHARED_DIR}"
    export NIGHTCRAFT_ENV_DIR="${ENV_DIR}"
    cd "${MINDMAP_SRC_DIR}"
    exec "${MINDMAP_VENV}/bin/uvicorn" main:app --host 127.0.0.1 --port 8000 --reload
  ) > "${LOG_DIR}/mindmap.log" 2>&1 &
  MINDMAP_PID=$!
  echo "${MINDMAP_PID}" > "${SHARED_DIR}/mindmap.pid"
  echo "${MINDMAP_PID}:mindmap" >> "${PROCS_FILE}"
  log "  mindmap started (PID ${MINDMAP_PID})"
fi

log "All services running. To stop: bash dev-setup/stop-all.sh"
log "View logs in ${LOG_DIR}/"
