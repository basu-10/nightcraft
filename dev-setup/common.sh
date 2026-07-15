#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ENV_DIR="${NIGHTCRAFT_ENV_DIR:-${REPO_ROOT}/.nightcraft-env}"
VENV_DIR="${NIGHTCRAFT_VENV_DIR:-${REPO_ROOT}/.nightcraft-venvs}"
SHARED_DIR="${NIGHTCRAFT_SHARED_DIR:-${REPO_ROOT}/.nightcraft-shared}"
ENV_SRC_DIR="${SCRIPT_DIR}/env-templates"

LOG_DIR="${NIGHTCRAFT_LOG_DIR:-${REPO_ROOT}/.nightcraft-logs}"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/nightcraft-dev-$(date +%Y%m%d_%H%M%S).log"

exec > >(tee -a "${LOG_FILE}")
exec 2>&1

AUTH_SRC_DIR="${REPO_ROOT}/service-auth"
RADIO_SRC_DIR="${REPO_ROOT}/app-radio"
NEERA_SRC_DIR="${REPO_ROOT}/app-artsy"
LANDING_SRC_DIR="${REPO_ROOT}/app-landing"
ADMIN_SRC_DIR="${REPO_ROOT}/app-admin"
GAME_SRC_DIR="${REPO_ROOT}/app-game"
NOTE_SRC_DIR="${REPO_ROOT}/app-note"
MINDMAP_SRC_DIR="${REPO_ROOT}/app-mindmap/backend"

AUTH_VENV="${VENV_DIR}/service-auth"
RADIO_VENV="${VENV_DIR}/dev-podcast-app"
NEERA_VENV="${VENV_DIR}/app-artsy"
LANDING_VENV="${VENV_DIR}/app-landing"
ADMIN_VENV="${VENV_DIR}/app-admin"
GAME_VENV="${VENV_DIR}/app-game"
NOTE_VENV="${VENV_DIR}/app-note"
MINDMAP_VENV="${VENV_DIR}/app-mindmap"

RADIO_SHARED="${SHARED_DIR}/dev-podcast-app"
AUTH_SHARED="${SHARED_DIR}/service-auth"
NEERA_SHARED="${SHARED_DIR}/app-artsy"

log()  { printf '[nightcraft-dev] %s\n' "$*"; }
warn() { printf '[nightcraft-dev] WARN: %s\n' "$*" >&2; }
die()  { printf '[nightcraft-dev] ERROR: %s\n' "$*" >&2; exit 1; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    die "Missing required command: $1"
  fi
}

require_file() {
  if [[ ! -f "$1" ]]; then
    die "Required file not found: $1"
  fi
}

ensure_dir() {
  mkdir -p "$1"
}

# Use uv for fully isolated Python environments. uv downloads and caches its own
# interpreter (NIGHTCRAFT_PYTHON_VERSION, default 3.12) under ~/.local/share/uv,
# so nothing is installed into the host OS.
setup_venv_and_deps() {
  local venv_dir="$1"
  local app_dir="$2"
  local venv_python="${venv_dir}/bin/python"
  local py_req="${NIGHTCRAFT_PYTHON_VERSION:-3.12}"

  require_cmd uv
  ensure_dir "${venv_dir}"

  if [[ ! -x "${venv_python}" ]] || ! "${venv_python}" -c 'import sys' >/dev/null 2>&1; then
    rm -rf "${venv_dir}"
    uv venv --python "${py_req}" "${venv_dir}"
    venv_python="${venv_dir}/bin/python"
  fi

  uv pip install --python "${venv_python}" --upgrade pip wheel setuptools
  uv pip install --python "${venv_python}" -r "${app_dir}/requirements.txt"
  uv pip install --python "${venv_python}" 'gunicorn>=22.0.0' 'psycopg[binary]>=3.1.0'
}

# Docker helper: use sudo if current user is not in docker group
docker_cmd() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

docker_compose_cmd() {
  if docker info >/dev/null 2>&1; then
    docker compose "$@"
  else
    sudo docker compose "$@"
  fi
}

is_docker_running() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  if sudo docker info >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

wait_for_pg() {
  local max_attempts=30
  local attempt=0
  until docker_cmd exec nightcraft-postgres pg_isready -U postgres >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [[ "${attempt}" -ge "${max_attempts}" ]]; then
      die "PostgreSQL did not become ready after ${max_attempts} attempts"
    fi
    sleep 1
  done
  log "PostgreSQL is ready"
}

wait_for_redis() {
  local max_attempts=15
  local attempt=0
  until docker_cmd exec nightcraft-redis redis-cli ping >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [[ "${attempt}" -ge "${max_attempts}" ]]; then
      die "Redis did not become ready after ${max_attempts} attempts"
    fi
    sleep 1
  done
  log "Redis is ready"
}