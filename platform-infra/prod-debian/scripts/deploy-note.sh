#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${NOTE_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-note.env"

log "Deploying app-note (NoteStack) from ${NOTE_SRC_DIR}"

setup_venv_and_deps "${NOTE_VENV_DIR}" "${NOTE_SRC_DIR}"

# Keep runtime app data and sync logs outside the source checkout.
ensure_dir "${NOTE_SHARED_DIR}"
ensure_dir "${NOTE_SHARED_DIR}/localappdata"
chown_tree "${NOTE_SHARED_DIR}"
chown_tree "${NOTE_VENV_DIR}"

# Enforce production NoteStack on PostgreSQL-only configuration.
(
	set -a
	source /etc/nightcraft/app-note.env
	set +a

	notestack_backend="${NOTESTACK_DB_BACKEND:-}"
	notestack_backend="$(printf '%s' "${notestack_backend}" | tr '[:upper:]' '[:lower:]' | xargs)"
	if [[ "${notestack_backend}" != "postgres" ]]; then
		echo "[deploy-note.sh] ERROR: NOTESTACK_DB_BACKEND must be set to postgres in /etc/nightcraft/app-note.env" >&2
		exit 1
	fi

	if [[ -z "${DATABASE_URL:-}" ]]; then
		echo "[deploy-note.sh] ERROR: DATABASE_URL must be set in /etc/nightcraft/app-note.env for PostgreSQL mode" >&2
		exit 1
	fi
)

log "app-note ready from ${NOTE_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-note.service"