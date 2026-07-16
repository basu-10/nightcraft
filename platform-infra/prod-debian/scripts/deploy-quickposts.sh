#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${QUICKPOSTS_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-quickposts.env"

log "Deploying app-quickposts (quickposts) from ${QUICKPOSTS_SRC_DIR}"

setup_venv_and_deps "${QUICKPOSTS_VENV_DIR}" "${QUICKPOSTS_SRC_DIR}"

# Keep runtime instance files outside the source checkout.
ensure_dir "${QUICKPOSTS_SHARED_DIR}/instance/uploads"
chown_tree "${QUICKPOSTS_SHARED_DIR}"
chown_tree "${QUICKPOSTS_VENV_DIR}"

log "Synchronizing quickposts PostgreSQL provisioning"
"${SCRIPT_DIR}/setup-postgres.sh"

log "Running quickposts setup CLI"
(
  cd "${QUICKPOSTS_SRC_DIR}"
  # Ensure setup uses the same runtime env as systemd service.
  set -a
  source /etc/nightcraft/app-quickposts.env
  set +a
  FLASK_AUTH_MODE="${FLASK_AUTH_MODE:-sso}" "${QUICKPOSTS_VENV_DIR}/bin/python" -m flask --app quickposts setup
)

log "quickposts ready from ${QUICKPOSTS_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-quickposts.service"
