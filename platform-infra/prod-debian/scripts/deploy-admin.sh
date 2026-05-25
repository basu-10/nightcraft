#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${ADMIN_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-admin.env"

log "Deploying app-admin from ${ADMIN_SRC_DIR}"

setup_venv_and_deps "${ADMIN_VENV_DIR}" "${ADMIN_SRC_DIR}"

# Keep runtime files outside the source checkout.
ensure_dir "${ADMIN_SHARED_DIR}"
chown_tree "${ADMIN_SHARED_DIR}"
chown_tree "${ADMIN_VENV_DIR}"

log "app-admin ready from ${ADMIN_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-admin.service"
