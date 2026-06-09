#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${SEEKSAGE_SRC_DIR}/backend/requirements.txt"
require_file "/etc/nightcraft/app-seeksage.env"

log "Deploying SeekSage backend from ${SEEKSAGE_SRC_DIR}"

backend_source_dir="${SEEKSAGE_SRC_DIR}/backend"

setup_venv_and_deps "${SEEKSAGE_VENV_DIR}" "${backend_source_dir}"

# Keep runtime state outside the source checkout.
ensure_dir "${SEEKSAGE_SHARED_DIR}/instance"

chown_tree "${SEEKSAGE_SHARED_DIR}"
chown_tree "${SEEKSAGE_VENV_DIR}"

# Build React frontend so the Workspace view (React SPA) is available.
log "Building SeekSage frontend …"
frontend_dir="${SEEKSAGE_SRC_DIR}/frontend"
if [[ -f "${frontend_dir}/package.json" ]]; then
  if command -v npm >/dev/null 2>&1; then
    cd "${frontend_dir}"
    npm ci 2>/dev/null || npm install
    VITE_BASE_PATH=/seeksage/ npm run build
    cd "${OLDPWD}"
    chown_tree "${frontend_dir}/dist"
    log "Frontend build complete."
  else
    log "WARNING: npm not found — skipping frontend build. Workspace view will fall back to dashboard."
  fi
fi

log "SeekSage ready from ${SEEKSAGE_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-seeksage.service"
