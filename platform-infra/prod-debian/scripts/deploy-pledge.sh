#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${PLEDGE_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-pledge.env"

log "Deploying app-pledge from ${PLEDGE_SRC_DIR}"

setup_venv_and_deps "${PLEDGE_VENV_DIR}" "${PLEDGE_SRC_DIR}"

# Keep runtime instance data outside the source checkout.
ensure_dir "${PLEDGE_SHARED_DIR}/instance"
chown_tree "${PLEDGE_SHARED_DIR}"
chown_tree "${PLEDGE_VENV_DIR}"

log "Running app-pledge setup CLI"
(
	set -a
	# Load production env so setup CLI sees PostgreSQL settings.
	. /etc/nightcraft/app-pledge.env
	set +a
	cd "${PLEDGE_SRC_DIR}"
	"${PLEDGE_VENV_DIR}/bin/python" -m flask --app greenpledge setup
)

log "app-pledge ready from ${PLEDGE_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-pledge.service"
