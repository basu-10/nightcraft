#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${SEEKSAGE_SRC_DIR}/backend/requirements.txt"
require_file "${SEEKSAGE_SRC_DIR}/frontend/package.json"
require_file "/etc/nightcraft/app-seeksage.env"

log "Deploying SeekSage backend from ${SEEKSAGE_SRC_DIR}"

backend_source_dir="${SEEKSAGE_SRC_DIR}/backend"
frontend_dist_dir="${SEEKSAGE_SRC_DIR}/frontend/dist"

require_cmd npm

log "Building SeekSage frontend"
(
	cd "${SEEKSAGE_SRC_DIR}/frontend"
	if [[ -f package-lock.json ]]; then
		npm ci
	else
		npm install
	fi
	VITE_BASE_PATH=/seeksage/ npm run build
)

setup_venv_and_deps "${SEEKSAGE_VENV_DIR}" "${backend_source_dir}"

# Keep runtime state outside the source checkout.
ensure_dir "${SEEKSAGE_SHARED_DIR}/instance"

# Backend serves frontend assets from this path.
if [[ -d "${frontend_dist_dir}" ]]; then
	chmod a+rx "${SEEKSAGE_SRC_DIR}" "${SEEKSAGE_SRC_DIR}/frontend" "${frontend_dist_dir}"
	chmod -R a+rX "${frontend_dist_dir}"
fi

chown_tree "${SEEKSAGE_SHARED_DIR}"
chown_tree "${SEEKSAGE_VENV_DIR}"

log "SeekSage ready from ${SEEKSAGE_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-seeksage.service"
