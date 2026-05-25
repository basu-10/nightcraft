#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${LANDING_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-landing.env"

log "Deploying app-landing from ${LANDING_SRC_DIR}"

setup_venv_and_deps "${LANDING_VENV_DIR}" "${LANDING_SRC_DIR}"

# Keep runtime files outside the source checkout.
ensure_dir "${LANDING_SHARED_DIR}"
chown_tree "${LANDING_SHARED_DIR}"
chown_tree "${LANDING_VENV_DIR}"

log "app-landing ready from ${LANDING_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-landing.service"
