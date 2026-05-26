#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${NOTE_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-note.env"

log "Deploying app-note (NoteStack) from ${NOTE_SRC_DIR}"

# Treat NoteStack as optional in environments where postgres wiring is not configured yet.
set -a
source /etc/nightcraft/app-note.env
set +a

notestack_backend="${NOTESTACK_DB_BACKEND:-}"
notestack_backend="$(printf '%s' "${notestack_backend}" | tr '[:upper:]' '[:lower:]' | xargs)"
if [[ "${notestack_backend}" != "postgres" ]]; then
	log "Skipping app-note deploy: NOTESTACK_DB_BACKEND is not set to postgres"
	exit 0
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
	log "Skipping app-note deploy: DATABASE_URL is missing in /etc/nightcraft/app-note.env"
	exit 0
fi

setup_venv_and_deps "${NOTE_VENV_DIR}" "${NOTE_SRC_DIR}"

# Keep runtime app data and sync logs outside the source checkout.
ensure_dir "${NOTE_SHARED_DIR}"
ensure_dir "${NOTE_SHARED_DIR}/localappdata"
chown_tree "${NOTE_SHARED_DIR}"
chown_tree "${NOTE_VENV_DIR}"

log "app-note ready from ${NOTE_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-note.service"