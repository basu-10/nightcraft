#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${NEERA_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-neera.env"

log "Deploying app-artsy (Neera) from ${NEERA_SRC_DIR}"

setup_venv_and_deps "${NEERA_VENV_DIR}" "${NEERA_SRC_DIR}"

# Keep runtime instance files outside the source checkout.
ensure_dir "${NEERA_SHARED_DIR}/instance/uploads/works"
chown_tree "${NEERA_SHARED_DIR}"
chown_tree "${NEERA_VENV_DIR}"

log "Running Neera setup CLI"
(
  cd "${NEERA_SRC_DIR}"
  # Ensure setup uses the same runtime env as systemd service.
  set -a
  source /etc/nightcraft/app-neera.env
  set +a
  FLASK_AUTH_MODE="${FLASK_AUTH_MODE:-sso}" "${NEERA_VENV_DIR}/bin/python" -m flask --app neera setup
)

log "Neera ready from ${NEERA_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-neera.service"
