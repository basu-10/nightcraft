#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${SCRATCHPAD_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-scratchpad.env"

log "Deploying app-scratchpad (scratchpad) from ${SCRATCHPAD_SRC_DIR}"

setup_venv_and_deps "${SCRATCHPAD_VENV_DIR}" "${SCRATCHPAD_SRC_DIR}"

# Keep runtime instance files outside the source checkout.
ensure_dir "${SCRATCHPAD_SHARED_DIR}/instance/uploads"
chown_tree "${SCRATCHPAD_SHARED_DIR}"
chown_tree "${SCRATCHPAD_VENV_DIR}"

log "Synchronizing scratchpad PostgreSQL provisioning"
"${SCRIPT_DIR}/setup-postgres.sh"

log "Running scratchpad setup CLI"
(
  cd "${SCRATCHPAD_SRC_DIR}"
  # Ensure setup uses the same runtime env as systemd service.
  set -a
  source /etc/nightcraft/app-scratchpad.env
  set +a
  FLASK_AUTH_MODE="${FLASK_AUTH_MODE:-sso}" "${SCRATCHPAD_VENV_DIR}/bin/python" -m flask --app scratchpad setup
)

log "scratchpad ready from ${SCRATCHPAD_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-scratchpad.service"
