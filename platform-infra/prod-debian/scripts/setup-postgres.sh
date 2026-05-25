#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./platform-infra/prod-debian/scripts/setup-postgres.sh"
  exit 1
fi

AUTH_DB_NAME="${AUTH_DB_NAME:-auth_db}"
AUTH_DB_USER="${AUTH_DB_USER:-auth_app}"
AUTH_DB_PASSWORD="${AUTH_DB_PASSWORD:-auth_app_db_2026_prod_secret}"

RADIO_DB_NAME="${RADIO_DB_NAME:-radio_db}"
RADIO_DB_USER="${RADIO_DB_USER:-radio_app}"
RADIO_DB_PASSWORD="${RADIO_DB_PASSWORD:-radio_app_db_2026_prod_secret}"

USERS_SQL="${PROD_DEBIAN_DIR}/postgres/users-and-permissions.sql"
DBS_SQL="${PROD_DEBIAN_DIR}/postgres/create-dbs.sql"

_fail_preflight() {
  echo "[setup-postgres] SQL template preflight failed: $1" >&2
  echo "[setup-postgres] Fix the SQL template and rerun this script." >&2
  echo "[setup-postgres] Checked files:" >&2
  echo "  - ${USERS_SQL}" >&2
  echo "  - ${DBS_SQL}" >&2
  exit 1
}

_validate_sql_template() {
  local file_path="$1"
  local short_name="$2"
  local problems=0
  local matches

  if [[ ! -f "${file_path}" ]]; then
    _fail_preflight "${short_name} is missing (${file_path})."
  fi

  if [[ ! -s "${file_path}" ]]; then
    _fail_preflight "${short_name} is empty (${file_path})."
  fi

  if matches="$(grep -nE '^[[:space:]]*\\[[:space:]]*$' "${file_path}" || true)"; [[ -n "${matches}" ]]; then
    echo "[setup-postgres] ${short_name}: orphan backslash command found:" >&2
    echo "${matches}" >&2
    problems=1
  fi

  if matches="$(grep -nE '^[[:space:]]*set[[:space:]]+ON_ERROR_STOP[[:space:]]+on([[:space:]]|$)' "${file_path}" || true)"; [[ -n "${matches}" ]]; then
    echo "[setup-postgres] ${short_name}: use '\\set ON_ERROR_STOP on' (missing leading backslash):" >&2
    echo "${matches}" >&2
    problems=1
  fi

  if ! grep -qE '^[[:space:]]*\\set[[:space:]]+ON_ERROR_STOP[[:space:]]+on([[:space:]]|$)' "${file_path}"; then
    echo "[setup-postgres] ${short_name}: missing required '\\set ON_ERROR_STOP on' directive." >&2
    problems=1
  fi

  if matches="$(grep -nE '\\[[:space:]]+gexec([[:space:]]|$)' "${file_path}" || true)"; [[ -n "${matches}" ]]; then
    echo "[setup-postgres] ${short_name}: invalid '\\ gexec' spacing, use '\\gexec':" >&2
    echo "${matches}" >&2
    problems=1
  fi

  if [[ "${problems}" -ne 0 ]]; then
    _fail_preflight "${short_name} contains malformed psql meta-commands."
  fi
}

_validate_sql_template "${USERS_SQL}" "users-and-permissions.sql"
_validate_sql_template "${DBS_SQL}" "create-dbs.sql"

sudo -u postgres psql \
  -v auth_db_user="${AUTH_DB_USER}" \
  -v auth_db_password="${AUTH_DB_PASSWORD}" \
  -v radio_db_user="${RADIO_DB_USER}" \
  -v radio_db_password="${RADIO_DB_PASSWORD}" \
  < "${USERS_SQL}"

sudo -u postgres psql \
  -v auth_db_name="${AUTH_DB_NAME}" \
  -v auth_db_user="${AUTH_DB_USER}" \
  -v radio_db_name="${RADIO_DB_NAME}" \
  -v radio_db_user="${RADIO_DB_USER}" \
  < "${DBS_SQL}"

echo "PostgreSQL roles and databases are ready."
