#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"

APP_USER="${APP_USER:-dev}"
APP_GROUP="${APP_GROUP:-${APP_USER}}"
INFRA_ROOT="${INFRA_ROOT:-/platform-infra}"
SHARED_ROOT="${SHARED_ROOT:-${INFRA_ROOT}/runtime/shared}"
VENV_ROOT="${VENV_ROOT:-${INFRA_ROOT}/runtime/venvs}"

RADIO_SLUG="${RADIO_SLUG:-dev-podcast-app}"
AUTH_SLUG="${AUTH_SLUG:-service-auth}"
LANDING_SLUG="${LANDING_SLUG:-app-landing}"
ADMIN_SLUG="${ADMIN_SLUG:-app-admin}"
CURIO_SLUG="${CURIO_SLUG:-app-artsy}"
SEEKSAGE_SLUG="${SEEKSAGE_SLUG:-seeksage-backend}"
GAME_SLUG="${GAME_SLUG:-app-game}"
NOTE_SLUG="${NOTE_SLUG:-app-note}"

RADIO_SRC_DIR="${RADIO_SRC_DIR:-${REPO_ROOT}/app-radio}"
AUTH_SRC_DIR="${AUTH_SRC_DIR:-${REPO_ROOT}/service-auth}"
LANDING_SRC_DIR="${LANDING_SRC_DIR:-${REPO_ROOT}/app-landing}"
ADMIN_SRC_DIR="${ADMIN_SRC_DIR:-${REPO_ROOT}/app-admin}"
CURIO_SRC_DIR="${CURIO_SRC_DIR:-${REPO_ROOT}/app-artsy}"
SEEKSAGE_SRC_DIR="${SEEKSAGE_SRC_DIR:-${REPO_ROOT}/app-researchAgent/seeksage}"
GAME_SRC_DIR="${GAME_SRC_DIR:-${REPO_ROOT}/app-game}"
NOTE_SRC_DIR="${NOTE_SRC_DIR:-${REPO_ROOT}/app-note}"

RADIO_SHARED_DIR="${SHARED_ROOT}/${RADIO_SLUG}"
AUTH_SHARED_DIR="${SHARED_ROOT}/${AUTH_SLUG}"
LANDING_SHARED_DIR="${SHARED_ROOT}/${LANDING_SLUG}"
ADMIN_SHARED_DIR="${SHARED_ROOT}/${ADMIN_SLUG}"
CURIO_SHARED_DIR="${SHARED_ROOT}/${CURIO_SLUG}"
SEEKSAGE_SHARED_DIR="${SHARED_ROOT}/${SEEKSAGE_SLUG}"
GAME_SHARED_DIR="${SHARED_ROOT}/${GAME_SLUG}"
NOTE_SHARED_DIR="${SHARED_ROOT}/${NOTE_SLUG}"
RADIO_VENV_DIR="${RADIO_VENV_DIR:-${VENV_ROOT}/${RADIO_SLUG}}"
AUTH_VENV_DIR="${AUTH_VENV_DIR:-${VENV_ROOT}/${AUTH_SLUG}}"
LANDING_VENV_DIR="${LANDING_VENV_DIR:-${VENV_ROOT}/${LANDING_SLUG}}"
ADMIN_VENV_DIR="${ADMIN_VENV_DIR:-${VENV_ROOT}/${ADMIN_SLUG}}"
CURIO_VENV_DIR="${CURIO_VENV_DIR:-${VENV_ROOT}/${CURIO_SLUG}}"
SEEKSAGE_VENV_DIR="${SEEKSAGE_VENV_DIR:-${VENV_ROOT}/${SEEKSAGE_SLUG}}"
GAME_VENV_DIR="${GAME_VENV_DIR:-${VENV_ROOT}/${GAME_SLUG}}"
NOTE_VENV_DIR="${NOTE_VENV_DIR:-${VENV_ROOT}/${NOTE_SLUG}}"

log() {
  printf '[%s] %s\n' "$(basename "$0")" "$*"
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Required file not found: $1" >&2
    exit 1
  fi
}

ensure_dir() {
  install -d -m 0755 "$1"
}

setup_venv_and_deps() {
  local venv_dir="$1"
  local app_dir="$2"

  require_cmd python3
  ensure_dir "${venv_dir}"

  if [[ ! -x "${venv_dir}/bin/python" ]]; then
    python3 -m venv "${venv_dir}"
  fi

  "${venv_dir}/bin/pip" install --upgrade pip wheel setuptools
  "${venv_dir}/bin/pip" install -r "${app_dir}/requirements.txt"
  "${venv_dir}/bin/pip" install 'gunicorn>=22.0.0' 'psycopg[binary]>=3.1.0'
}

chown_tree() {
  local target_dir="$1"
  if [[ "${EUID}" -eq 0 ]]; then
    chown -R "${APP_USER}:${APP_GROUP}" "${target_dir}"
  fi
}
