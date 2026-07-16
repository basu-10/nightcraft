#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${ALFRED_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-alfred.env"

log "Deploying app-alfred (Alfred) from ${ALFRED_SRC_DIR}"

setup_venv_and_deps "${ALFRED_VENV_DIR}" "${ALFRED_SRC_DIR}"

# Keep runtime instance files outside the source checkout.
ensure_dir "${ALFRED_SHARED_DIR}/instance/uploads/assets"
ensure_dir "${ALFRED_SHARED_DIR}/instance/uploads/reports"
chown_tree "${ALFRED_SHARED_DIR}"
chown_tree "${ALFRED_VENV_DIR}"

log "Synchronizing Alfred PostgreSQL provisioning"
"${SCRIPT_DIR}/setup-postgres.sh"

log "Running Alfred setup CLI"
(
  cd "${ALFRED_SRC_DIR}"
  # Ensure setup uses the same runtime env as systemd service.
  set -a
  source /etc/nightcraft/app-alfred.env
  set +a
  FLASK_AUTH_MODE="${FLASK_AUTH_MODE:-sso}" "${ALFRED_VENV_DIR}/bin/python" -m flask --app alfred setup
)

log "Alfred ready from ${ALFRED_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-alfred.service"
