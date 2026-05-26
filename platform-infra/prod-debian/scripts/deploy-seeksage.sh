#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${SEEKSAGE_SRC_DIR}/backend/requirements.txt"
require_file "/etc/nightcraft/app-seeksage.env"

log "Deploying SeekSage backend from ${SEEKSAGE_SRC_DIR}"

backend_source_dir="${SEEKSAGE_SRC_DIR}/backend"

setup_venv_and_deps "${SEEKSAGE_VENV_DIR}" "${backend_source_dir}"

# Keep runtime state outside the source checkout.
ensure_dir "${SEEKSAGE_SHARED_DIR}/instance"

chown_tree "${SEEKSAGE_SHARED_DIR}"
chown_tree "${SEEKSAGE_VENV_DIR}"

log "SeekSage ready from ${SEEKSAGE_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-seeksage.service"
