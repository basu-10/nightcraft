#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${GAME_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-game.env"

log "Deploying app-game from ${GAME_SRC_DIR}"

setup_venv_and_deps "${GAME_VENV_DIR}" "${GAME_SRC_DIR}"

# Keep runtime files outside the source checkout.
ensure_dir "${GAME_SHARED_DIR}"
chown_tree "${GAME_SHARED_DIR}"
chown_tree "${GAME_VENV_DIR}"

log "app-game ready from ${GAME_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-game.service"
