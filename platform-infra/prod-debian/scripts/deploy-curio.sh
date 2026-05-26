#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${CURIO_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-curio.env"

log "Deploying app-artsy (Curio) from ${CURIO_SRC_DIR}"

setup_venv_and_deps "${CURIO_VENV_DIR}" "${CURIO_SRC_DIR}"

# Keep runtime instance files outside the source checkout.
ensure_dir "${CURIO_SHARED_DIR}/instance/uploads/works"
chown_tree "${CURIO_SHARED_DIR}"
chown_tree "${CURIO_VENV_DIR}"

log "Running Curio setup CLI"
(
  cd "${CURIO_SRC_DIR}"
  # Ensure setup uses the same runtime env as systemd service.
  set -a
  source /etc/nightcraft/app-curio.env
  set +a
  FLASK_AUTH_MODE="${FLASK_AUTH_MODE:-sso}" "${CURIO_VENV_DIR}/bin/python" -m flask --app curio setup
)

log "Curio ready from ${CURIO_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-curio.service"
