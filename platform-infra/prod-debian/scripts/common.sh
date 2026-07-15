#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"

APP_USER="${APP_USER:-dev}"
APP_GROUP="${APP_GROUP:-${APP_USER}}"
SOURCE_ROOT="${SOURCE_ROOT:-/nightcraft-source-code}"
RUNTIME_ROOT="${RUNTIME_ROOT:-/runtime}"
SHARED_ROOT="${SHARED_ROOT:-${RUNTIME_ROOT}/shared}"
VENV_ROOT="${VENV_ROOT:-${RUNTIME_ROOT}/venvs}"

RADIO_SLUG="${RADIO_SLUG:-dev-podcast-app}"
AUTH_SLUG="${AUTH_SLUG:-service-auth}"
LANDING_SLUG="${LANDING_SLUG:-app-landing}"
ADMIN_SLUG="${ADMIN_SLUG:-app-admin}"
NEERA_SLUG="${NEERA_SLUG:-app-artsy}"
GAME_SLUG="${GAME_SLUG:-app-game}"
NOTE_SLUG="${NOTE_SLUG:-app-note}"
PLEDGE_SLUG="${PLEDGE_SLUG:-green-pledge-app}"

RADIO_SRC_DIR="${RADIO_SRC_DIR:-${REPO_ROOT}/app-radio}"
AUTH_SRC_DIR="${AUTH_SRC_DIR:-${REPO_ROOT}/service-auth}"
LANDING_SRC_DIR="${LANDING_SRC_DIR:-${REPO_ROOT}/app-landing}"
ADMIN_SRC_DIR="${ADMIN_SRC_DIR:-${REPO_ROOT}/app-admin}"
NEERA_SRC_DIR="${NEERA_SRC_DIR:-${REPO_ROOT}/app-artsy}"
GAME_SRC_DIR="${GAME_SRC_DIR:-${REPO_ROOT}/app-game}"
NOTE_SRC_DIR="${NOTE_SRC_DIR:-${REPO_ROOT}/app-note}"
PLEDGE_SRC_DIR="${PLEDGE_SRC_DIR:-${REPO_ROOT}/app-pledge}"

RADIO_SHARED_DIR="${SHARED_ROOT}/${RADIO_SLUG}"
AUTH_SHARED_DIR="${SHARED_ROOT}/${AUTH_SLUG}"
LANDING_SHARED_DIR="${SHARED_ROOT}/${LANDING_SLUG}"
ADMIN_SHARED_DIR="${SHARED_ROOT}/${ADMIN_SLUG}"
NEERA_SHARED_DIR="${SHARED_ROOT}/${NEERA_SLUG}"
GAME_SHARED_DIR="${SHARED_ROOT}/${GAME_SLUG}"
NOTE_SHARED_DIR="${SHARED_ROOT}/${NOTE_SLUG}"
PLEDGE_SHARED_DIR="${SHARED_ROOT}/${PLEDGE_SLUG}"
RADIO_VENV_DIR="${RADIO_VENV_DIR:-${VENV_ROOT}/${RADIO_SLUG}}"
AUTH_VENV_DIR="${AUTH_VENV_DIR:-${VENV_ROOT}/${AUTH_SLUG}}"
LANDING_VENV_DIR="${LANDING_VENV_DIR:-${VENV_ROOT}/${LANDING_SLUG}}"
ADMIN_VENV_DIR="${ADMIN_VENV_DIR:-${VENV_ROOT}/${ADMIN_SLUG}}"
NEERA_VENV_DIR="${NEERA_VENV_DIR:-${VENV_ROOT}/${NEERA_SLUG}}"
GAME_VENV_DIR="${GAME_VENV_DIR:-${VENV_ROOT}/${GAME_SLUG}}"
NOTE_VENV_DIR="${NOTE_VENV_DIR:-${VENV_ROOT}/${NOTE_SLUG}}"
PLEDGE_VENV_DIR="${PLEDGE_VENV_DIR:-${VENV_ROOT}/${PLEDGE_SLUG}}"

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
  local venv_python="${venv_dir}/bin/python"

  require_cmd python3
  ensure_dir "${venv_dir}"

  if [[ ! -x "${venv_python}" ]] || ! "${venv_python}" -c 'import sys' >/dev/null 2>&1; then
    rm -rf "${venv_dir}"
    python3 -m venv "${venv_dir}"
    venv_python="${venv_dir}/bin/python"
  fi

  if ! "${venv_python}" -m pip --version >/dev/null 2>&1; then
    "${venv_python}" -m ensurepip --upgrade
  fi

  "${venv_python}" -m pip install --upgrade pip wheel setuptools
  "${venv_python}" -m pip install -r "${app_dir}/requirements.txt"
  "${venv_python}" -m pip install 'gunicorn>=22.0.0' 'psycopg[binary]>=3.1.0'
}

chown_tree() {
  local target_dir="$1"
  if [[ "${EUID}" -eq 0 ]]; then
    chown -R "${APP_USER}:${APP_GROUP}" "${target_dir}"
  fi
}

# --- Product manifest helpers (source of truth: products.yml) ---
# Reads via scripts/products.py so bash and the runtime manager share one source.

PRODUCTS_PY="${SCRIPT_DIR}/products.py"

nc_products_manifest() {
  # Prefer an explicit env override, then the deployed path, then repo copy.
  if [[ -n "${NC_PRODUCTS_YML:-}" ]]; then
    echo "${NC_PRODUCTS_YML}"
  elif [[ -f /etc/nightcraft/products.yml ]]; then
    echo /etc/nightcraft/products.yml
  else
    echo "${PROD_DEBIAN_DIR}/products.yml"
  fi
}

nc_field() {
  local slug="$1" field="$2"
  python3 "${PRODUCTS_PY}" --manifest "$(nc_products_manifest)" get "${slug}" "${field}"
}

nc_policy()      { nc_field "$1" runtime.policy; }
nc_service()     { nc_field "$1" runtime.service; }
nc_port()        { nc_field "$1" runtime.port; }
nc_workers()     { nc_field "$1" runtime.workers; }
nc_upstream()    { nc_field "$1" runtime.upstream; }
nc_idle()        { nc_field "$1" runtime.idle_timeout; }

nc_public_paths() {
  python3 "${PRODUCTS_PY}" --manifest "$(nc_products_manifest)" public_paths "$1"
}

nc_slugs() {
  python3 "${PRODUCTS_PY}" --manifest "$(nc_products_manifest)" slugs "$@"
}

nc_is_on_demand() {
  [[ "$(nc_policy "$1")" == "on_demand" ]]
}
