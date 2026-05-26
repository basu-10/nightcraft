#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

CURIO_ENV_FILE="${CURIO_ENV_FILE:-/etc/nightcraft/app-curio.env}"
CURIO_RESTART_SERVICE="${CURIO_RESTART_SERVICE:-nightcraft-curio.service}"
CURIO_NEW_PASSWORD="${CURIO_NEW_PASSWORD:-}"

usage() {
  cat <<'EOF'
Usage:
  sudo reset-curio-password.sh [--password NEW_PASSWORD] [--no-restart]

Purpose:
  Rotate the Curio PostgreSQL role password, update /etc/nightcraft/app-curio.env,
  resync PostgreSQL provisioning, and restart the Curio service.
EOF
}

NO_RESTART=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --password)
      CURIO_NEW_PASSWORD="${2:-}"
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

require_file "${CURIO_ENV_FILE}"
require_file "${PROD_DEBIAN_DIR}/scripts/setup-postgres.sh"

if [[ -z "${CURIO_NEW_PASSWORD}" ]]; then
  require_cmd openssl
  CURIO_NEW_PASSWORD="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)"
fi

if [[ -z "${CURIO_NEW_PASSWORD}" ]]; then
  echo "Failed to generate a new Curio password." >&2
  exit 1
fi

python3 - "${CURIO_ENV_FILE}" "${CURIO_NEW_PASSWORD}" <<'PY'
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

log "Updated ${CURIO_ENV_FILE} with a new Curio DB password"

AUTH_DB_PASSWORD="${AUTH_DB_PASSWORD:-auth_app_db_2026_prod_secret}" \
RADIO_DB_PASSWORD="${RADIO_DB_PASSWORD:-radio_app_db_2026_prod_secret}" \
CURIO_DB_PASSWORD="${CURIO_NEW_PASSWORD}" \
SEEKSAGE_DB_PASSWORD="${SEEKSAGE_DB_PASSWORD:-}" \
NOTESTACK_DB_PASSWORD="${NOTESTACK_DB_PASSWORD:-}" \
  "${SCRIPT_DIR}/setup-postgres.sh"

if [[ "${NO_RESTART}" -eq 0 ]]; then
  if command -v systemctl >/dev/null 2>&1; then
    systemctl restart "${CURIO_RESTART_SERVICE}"
    log "Restarted ${CURIO_RESTART_SERVICE}"
  else
    log "systemctl not available; skip restart"
  fi
fi

printf 'Curio password reset complete. New password: %s\n' "${CURIO_NEW_PASSWORD}"