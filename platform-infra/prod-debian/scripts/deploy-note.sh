#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "${NOTE_SRC_DIR}/requirements.txt"
require_file "/etc/nightcraft/app-note.env"

log "Deploying app-note (NoteStack) from ${NOTE_SRC_DIR}"

set -a
source /etc/nightcraft/app-note.env
set +a

notestack_backend="${NOTESTACK_DB_BACKEND:-}"
notestack_backend="$(printf '%s' "${notestack_backend}" | tr '[:upper:]' '[:lower:]' | xargs)"
if [[ "${notestack_backend}" != "postgres" ]]; then
	echo "[deploy-note.sh] ERROR: NOTESTACK_DB_BACKEND must be set to postgres in /etc/nightcraft/app-note.env" >&2
	exit 1
fi

notestack_db_name="${NOTESTACK_DB_NAME:-notestack_db}"
notestack_db_user="${NOTESTACK_DB_USER:-notestack_app}"
notestack_db_password="${NOTESTACK_DB_PASSWORD:-notestack_app_db_2026_prod_secret}"

if [[ -z "${DATABASE_URL:-}" ]]; then
	DATABASE_URL="postgresql://${notestack_db_user}:${notestack_db_password}@127.0.0.1:5432/${notestack_db_name}"
	export DATABASE_URL
	log "Derived NoteStack DATABASE_URL from PostgreSQL defaults"
fi

# Persist derived DATABASE_URL back to env file so systemd service picks it up.
if ! grep -qE "^DATABASE_URL=" /etc/nightcraft/app-note.env 2>/dev/null; then
	# Replace commented-out DATABASE_URL line; else append.
	if grep -qE "^\s*#\s*DATABASE_URL=" /etc/nightcraft/app-note.env 2>/dev/null; then
		awk -v val="DATABASE_URL=${DATABASE_URL}" \
			'{if (/^\s*#\s*DATABASE_URL=/) print val; else print}' \
			/etc/nightcraft/app-note.env > /tmp/app-note.env.tmp \
			&& mv /tmp/app-note.env.tmp /etc/nightcraft/app-note.env
	else
		echo "DATABASE_URL=${DATABASE_URL}" >> /etc/nightcraft/app-note.env
	fi
fi

setup_venv_and_deps "${NOTE_VENV_DIR}" "${NOTE_SRC_DIR}"

# Keep runtime app data and sync logs outside the source checkout.
ensure_dir "${NOTE_SHARED_DIR}"
ensure_dir "${NOTE_SHARED_DIR}/localappdata"
chown_tree "${NOTE_SHARED_DIR}"
chown_tree "${NOTE_VENV_DIR}"

log "app-note ready from ${NOTE_SRC_DIR}"
log "Run sudo systemctl restart nightcraft-note.service"