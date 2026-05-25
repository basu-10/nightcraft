#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${AUTH_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/service-auth.env"

log "Deploying service-auth from ${AUTH_SRC_DIR}"

setup_venv_and_deps "${AUTH_VENV_DIR}" "${AUTH_SRC_DIR}"

# Persist auth signing keys outside the source checkout.
ensure_dir "${AUTH_SHARED_DIR}/keys"
chown_tree "${AUTH_SHARED_DIR}"
chown_tree "${AUTH_VENV_DIR}"

log "service-auth ready from ${AUTH_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-auth.service"
