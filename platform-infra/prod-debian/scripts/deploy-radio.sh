#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${RADIO_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-radio.env"

log "Deploying app-radio from ${RADIO_SRC_DIR}"

setup_venv_and_deps "${RADIO_VENV_DIR}" "${RADIO_SRC_DIR}"

# Keep runtime instance data outside the source checkout.
ensure_dir "${RADIO_SHARED_DIR}/instance/uploads/works"
ensure_dir "${RADIO_SHARED_DIR}/instance/automation_logs"
chown_tree "${RADIO_SHARED_DIR}"
chown_tree "${RADIO_VENV_DIR}"

log "Running app-radio setup CLI"
(
	set -a
	# Load production env so setup CLI sees PostgreSQL settings.
	. /etc/nightcraft/app-radio.env
	set +a
	cd "${RADIO_SRC_DIR}"
	"${RADIO_VENV_DIR}/bin/flask" --app devradio setup
)

log "app-radio ready from ${RADIO_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-radio.service"
