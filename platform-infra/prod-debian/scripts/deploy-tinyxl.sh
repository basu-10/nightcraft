#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

SPREADSHEET_SLUG="${SPREADSHEET_SLUG:-app-spreadsheet}"
SPREADSHEET_SRC_DIR="${SPREADSHEET_SRC_DIR:-${REPO_ROOT}/app-spreadsheet}"
SPREADSHEET_SHARED_DIR="${SPREADSHEET_SHARED_DIR:-${SHARED_ROOT}/${SPREADSHEET_SLUG}}"
SPREADSHEET_VENV_DIR="${SPREADSHEET_VENV_DIR:-${VENV_ROOT}/${SPREADSHEET_SLUG}}"

require_file "${SPREADSHEET_SRC_DIR}/requirements.txt"
require_file "${SPREADSHEET_SRC_DIR}/tinyXL.py"
require_file "/etc/nightcraft/tinyxl.env"

log "Deploying app-spreadsheet (TinyXL) from ${SPREADSHEET_SRC_DIR}"

setup_venv_and_deps "${SPREADSHEET_VENV_DIR}" "${SPREADSHEET_SRC_DIR}"

# Keep uploads + SQLite state outside the source checkout.
ensure_dir "${SPREADSHEET_SHARED_DIR}"
ensure_dir "${SPREADSHEET_SHARED_DIR}/uploads"
ensure_dir "${SPREADSHEET_SHARED_DIR}/db"
chown_tree "${SPREADSHEET_SHARED_DIR}"
chown_tree "${SPREADSHEET_VENV_DIR}"

log "app-spreadsheet ready from ${SPREADSHEET_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-tinyxl.service"
