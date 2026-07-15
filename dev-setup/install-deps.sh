#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

log "Installing Python dependencies for all services"

ensure_dir "${SHARED_DIR}"
ensure_dir "${AUTH_SHARED}/keys"

log "  service-auth..."
setup_venv_and_deps "${AUTH_VENV}" "${AUTH_SRC_DIR}"

log "  app-radio..."
setup_venv_and_deps "${RADIO_VENV}" "${RADIO_SRC_DIR}"

log "  app-neera..."
setup_venv_and_deps "${NEERA_VENV}" "${NEERA_SRC_DIR}"

log "  app-landing..."
setup_venv_and_deps "${LANDING_VENV}" "${LANDING_SRC_DIR}"

log "  app-admin..."
setup_venv_and_deps "${ADMIN_VENV}" "${ADMIN_SRC_DIR}"

log "  app-game..."
setup_venv_and_deps "${GAME_VENV}" "${GAME_SRC_DIR}"

log "  app-note..."
setup_venv_and_deps "${NOTE_VENV}" "${NOTE_SRC_DIR}"

log "  app-mindmap..."
setup_venv_and_deps "${MINDMAP_VENV}" "${MINDMAP_SRC_DIR}"

log "All Python dependencies installed"