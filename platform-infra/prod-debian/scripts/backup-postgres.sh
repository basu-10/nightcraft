#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/nightcraft-postgres}"
TS="$(date +%Y%m%d-%H%M%S)"

AUTH_DB_NAME="${AUTH_DB_NAME:-auth_db}"
RADIO_DB_NAME="${RADIO_DB_NAME:-radio_db}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./nightcraft-source-code/platform-infra/prod-debian/scripts/backup-postgres.sh"
  exit 1
fi

install -d -m 0750 "${BACKUP_ROOT}"

sudo -u postgres pg_dump -Fc "${AUTH_DB_NAME}" > "${BACKUP_ROOT}/${AUTH_DB_NAME}-${TS}.dump"
sudo -u postgres pg_dump -Fc "${RADIO_DB_NAME}" > "${BACKUP_ROOT}/${RADIO_DB_NAME}-${TS}.dump"

echo "Backups written to ${BACKUP_ROOT}"
