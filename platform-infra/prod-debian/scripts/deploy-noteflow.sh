#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${NOTEFLOW_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-noteflow.env"

log "Deploying app-noteflow (noteflow) from ${NOTEFLOW_SRC_DIR}"

setup_venv_and_deps "${NOTEFLOW_VENV_DIR}" "${NOTEFLOW_SRC_DIR}"

# Keep runtime instance files outside the source checkout.
ensure_dir "${NOTEFLOW_SHARED_DIR}/instance/uploads"
chown_tree "${NOTEFLOW_SHARED_DIR}"
chown_tree "${NOTEFLOW_VENV_DIR}"

log "Synchronizing noteflow PostgreSQL provisioning"
"${SCRIPT_DIR}/setup-postgres.sh"

log "Running noteflow setup CLI"
(
  cd "${NOTEFLOW_SRC_DIR}"
  # Ensure setup uses the same runtime env as systemd service.
  set -a
  source /etc/nightcraft/app-noteflow.env
  set +a
  FLASK_AUTH_MODE="${FLASK_AUTH_MODE:-sso}" "${NOTEFLOW_VENV_DIR}/bin/python" -m flask --app noteflow setup
)

log "noteflow ready from ${NOTEFLOW_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-noteflow.service"
