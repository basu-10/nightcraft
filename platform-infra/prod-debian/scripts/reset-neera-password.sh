#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

NEERA_ENV_FILE="${NEERA_ENV_FILE:-/etc/nightcraft/app-neera.env}"
NEERA_RESTART_SERVICE="${NEERA_RESTART_SERVICE:-nightcraft-neera.service}"
NEERA_NEW_PASSWORD="${NEERA_NEW_PASSWORD:-}"

sync_repo() {
  if [[ ! -d "${REPO_ROOT}/.git" ]]; then
    echo "Expected git checkout at ${REPO_ROOT}, but no .git directory was found." >&2
    exit 1
  fi

  log "Syncing repository in ${REPO_ROOT}"
  git -C "${REPO_ROOT}" pull --ff-only
}

usage() {
  cat <<'EOF'
Usage:
  sudo reset-neera-password.sh [--password NEW_PASSWORD] [--no-restart]

Purpose:
  Rotate the neera PostgreSQL role password, update /etc/nightcraft/app-neera.env,
  resync PostgreSQL provisioning, and restart the neera service.
EOF
}

NO_RESTART=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --password)
      NEERA_NEW_PASSWORD="${2:-}"
      shift
      ;;
    --no-restart)
      NO_RESTART=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

require_file "${NEERA_ENV_FILE}"
require_file "${PROD_DEBIAN_DIR}/scripts/setup-postgres.sh"
sync_repo

if [[ -z "${NEERA_NEW_PASSWORD}" ]]; then
  require_cmd openssl
  NEERA_NEW_PASSWORD="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)"
fi

if [[ -z "${NEERA_NEW_PASSWORD}" ]]; then
  echo "Failed to generate a new neera password." >&2
  exit 1
fi

python3 - "${NEERA_ENV_FILE}" "${NEERA_NEW_PASSWORD}" <<'PY'
from __future__ import annotations

import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
new_password = sys.argv[2]

text = path.read_text(encoding="utf-8")
pattern = re.compile(r'^(DATABASE_URL=postgresql(?:\+[^:]*)?://[^:]+:)([^@]+)(@.*)$', re.MULTILINE)
match = pattern.search(text)
if not match:
    raise SystemExit(f"DATABASE_URL not found in {path}")

updated = pattern.sub(rf'\1{new_password}\3', text, count=1)
path.write_text(updated, encoding="utf-8")
PY

log "Updated ${NEERA_ENV_FILE} with a new neera DB password"

AUTH_DB_PASSWORD="${AUTH_DB_PASSWORD:-auth_app_db_2026_prod_secret}" \
RADIO_DB_PASSWORD="${RADIO_DB_PASSWORD:-radio_app_db_2026_prod_secret}" \
NEERA_DB_PASSWORD="${NEERA_NEW_PASSWORD}" \
NOTESTACK_DB_PASSWORD="${NOTESTACK_DB_PASSWORD:-}" \
  "${SCRIPT_DIR}/setup-postgres.sh"

if [[ "${NO_RESTART}" -eq 0 ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl restart "${NEERA_RESTART_SERVICE}"
    log "Restarted ${NEERA_RESTART_SERVICE}"
  else
    log "systemctl not available; skip restart"
  fi
fi

printf 'neera password reset complete. New password: %s\n' "${NEERA_NEW_PASSWORD}"