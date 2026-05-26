#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./nightcraft-source-code/platform-infra/prod-debian/scripts/backup-all.sh" >&2
  exit 1
fi

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/nightcraft}"
STAMP="$(date +%Y%m%d_%H%M%S)"
DEST_DIR="${BACKUP_ROOT}/${STAMP}"

install -d -m 0750 "${DEST_DIR}"

APP_DATA_ARCHIVE="${DEST_DIR}/app-shared-data.tar.gz"
ENV_ARCHIVE="${DEST_DIR}/etc-nightcraft-env.tar.gz"

# Backup shared app data (if present)
mapfile -t shared_dirs < <(find "${SHARED_ROOT}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null || true)
if [[ "${#shared_dirs[@]}" -gt 0 ]]; then
  tar -czf "${APP_DATA_ARCHIVE}" "${shared_dirs[@]}"
  log "Saved shared app data: ${APP_DATA_ARCHIVE}"
else
  log "No shared app data directories found under ${SHARED_ROOT}"
fi

# Ensure NoteStack shared dir is included (may not be under SHARED_ROOT pattern)
if [[ -d "${NOTE_SHARED_DIR}" ]]; then
  tar -czf "${APP_DATA_ARCHIVE}.note" "${NOTE_SHARED_DIR}"
  log "Saved NoteStack shared data: ${APP_DATA_ARCHIVE}.note"
fi

# Backup runtime env files
if [[ -d /etc/nightcraft ]]; then
  tar -czf "${ENV_ARCHIVE}" /etc/nightcraft
  log "Saved env config: ${ENV_ARCHIVE}"
else
  log "No /etc/nightcraft directory found"
fi

# Ensure NoteStack env file is backed up separately if not caught above
if [[ -f /etc/nightcraft/app-note.env ]] && [[ ! -f "${ENV_ARCHIVE}" ]]; then
  tar -czf "${ENV_ARCHIVE}" /etc/nightcraft/app-note.env
  log "Saved NoteStack env config: ${ENV_ARCHIVE}"
fi

# Backup postgres logical dumps using existing script
BACKUP_DIR="${DEST_DIR}/postgres" "${SCRIPT_DIR}/backup-postgres.sh"

log "Full backup complete at ${DEST_DIR}"
