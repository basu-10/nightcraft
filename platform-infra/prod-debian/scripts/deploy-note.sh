#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${NOTE_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-note.env"

log "Deploying app-note (NoteStack) from ${NOTE_SRC_DIR}"

setup_venv_and_deps "${NOTE_VENV_DIR}" "${NOTE_SRC_DIR}"

# Keep runtime sqlite and sync logs outside the source checkout.
ensure_dir "${NOTE_SHARED_DIR}"
ensure_dir "${NOTE_SHARED_DIR}/localappdata"
chown_tree "${NOTE_SHARED_DIR}"
chown_tree "${NOTE_VENV_DIR}"

log "app-note ready from ${NOTE_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-note.service"