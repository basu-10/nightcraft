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
	"${RADIO_VENV_DIR}/bin/python" -m flask --app devradio setup
)

log "app-radio ready from ${RADIO_SRC_DIR}"
log "Restarting nightcraft-radio.service"
systemctl restart nightcraft-radio.service

# Ensure the ingestion timer unit files exist on this host. They are installed
# by install-systemd.sh, but a deploy must not fail if that hasn't been re-run
# since the units were added. Install idempotently, then enable the timer.
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INGEST_SERVICE_SRC="${PROD_DEBIAN_DIR}/systemd/nightcraft-radio-ingest.service"
INGEST_TIMER_SRC="${PROD_DEBIAN_DIR}/systemd/nightcraft-radio-ingest.timer"
if [[ -f "${INGEST_SERVICE_SRC}" && -f "${INGEST_TIMER_SRC}" ]]; then
  install -m 0644 "${INGEST_SERVICE_SRC}" /etc/systemd/system/nightcraft-radio-ingest.service
  install -m 0644 "${INGEST_TIMER_SRC}" /etc/systemd/system/nightcraft-radio-ingest.timer
  systemctl daemon-reload
fi

log "Enabling nightcraft-radio-ingest.timer (hourly ingestion, out of gunicorn)"
systemctl enable --now nightcraft-radio-ingest.timer

log "Deployment complete. Verify: systemctl status nightcraft-radio.service nightcraft-radio-ingest.timer"
