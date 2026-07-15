#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./nightcraft-source-code/platform-infra/prod-debian/scripts/setup-postgres.sh"
  exit 1
fi

AUTH_DB_NAME="${AUTH_DB_NAME:-auth_db}"
AUTH_DB_USER="${AUTH_DB_USER:-auth_app}"
AUTH_DB_PASSWORD="${AUTH_DB_PASSWORD:-auth_app_db_2026_prod_secret}"

RADIO_DB_NAME="${RADIO_DB_NAME:-radio_db}"
RADIO_DB_USER="${RADIO_DB_USER:-radio_app}"
RADIO_DB_PASSWORD="${RADIO_DB_PASSWORD:-radio_app_db_2026_prod_secret}"

NEERA_DB_NAME="${NEERA_DB_NAME:-}"
NEERA_DB_USER="${NEERA_DB_USER:-}"
NEERA_DB_PASSWORD="${NEERA_DB_PASSWORD:-}"

NOTESTACK_DB_NAME="${NOTESTACK_DB_NAME:-}"
NOTESTACK_DB_USER="${NOTESTACK_DB_USER:-}"
NOTESTACK_DB_PASSWORD="${NOTESTACK_DB_PASSWORD:-}"

NEERA_ENV_FILE="${NEERA_ENV_FILE:-/etc/nightcraft/app-neera.env}"
NOTESTACK_ENV_FILE="${NOTESTACK_ENV_FILE:-/etc/nightcraft/app-note.env}"

PLEDGE_DB_NAME="${PLEDGE_DB_NAME:-green_pledge_db}"
PLEDGE_DB_USER="${PLEDGE_DB_USER:-green_pledge_app}"
PLEDGE_DB_PASSWORD="${PLEDGE_DB_PASSWORD:-green_pledge_app_db_2026_prod_secret}"
PLEDGE_ENV_FILE="${PLEDGE_ENV_FILE:-/etc/nightcraft/app-pledge.env}"

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

_extract_env_value_from_file() {
  local env_file="$1"
  local key="$2"
  local line value

  if [[ ! -f "${env_file}" ]]; then
    return 1
  fi

  line="$(grep -E "^[[:space:]]*${key}=" "${env_file}" | tail -n 1 || true)"
  if [[ -z "${line}" ]]; then
    return 1
  fi

  value="${line#*=}"
  value="${value%$'\r'}"
  value="${value%\"}"
  value="${value#\"}"
  value="${value%\'}"
  value="${value#\'}"

  printf '%s' "${value}"
}

_extract_database_url_from_env_file() {
  local env_file="$1"
  local key value

  for key in DATABASE_URL FLASK_SQLALCHEMY_DATABASE_URI SQLALCHEMY_DATABASE_URI; do
    if value="$(_extract_env_value_from_file "${env_file}" "${key}")"; then
      printf '%s' "${value}"
      return 0
    fi
  done

  return 1
}

_set_db_values_from_url() {
  local database_url="$1"
  local prefix="$2"
  local rest credentials user password host_and_path db_name

  if [[ "${database_url}" == postgresql+*://* ]]; then
    rest="${database_url#postgresql+*://}"
  elif [[ "${database_url}" == postgresql://* ]]; then
    rest="${database_url#postgresql://}"
  elif [[ "${database_url}" == postgres://* ]]; then
    rest="${database_url#postgres://}"
  else
    return 1
  fi

  if [[ "${rest}" != *@* ]]; then
    return 1
  fi

  credentials="${rest%%@*}"
  host_and_path="${rest#*@}"

  user="${credentials%%:*}"
  if [[ "${credentials}" == *:* ]]; then
    password="${credentials#*:}"
  else
    password=""
  fi

  if [[ "${host_and_path}" != */* ]]; then
    return 1
  fi

  db_name="${host_and_path#*/}"
  db_name="${db_name%%\?*}"
  db_name="${db_name%%#*}"

  if [[ -z "${user}" || -z "${db_name}" ]]; then
    return 1
  fi

  printf -v "${prefix}_DB_USER" '%s' "${user}"
  printf -v "${prefix}_DB_PASSWORD" '%s' "${password}"
  printf -v "${prefix}_DB_NAME" '%s' "${db_name}"
}

if [[ -z "${NEERA_DB_USER}" || -z "${NEERA_DB_NAME}" || -z "${NEERA_DB_PASSWORD}" ]]; then
  if neera_url="$(_extract_database_url_from_env_file "${NEERA_ENV_FILE}")"; then
    _set_db_values_from_url "${neera_url}" "NEERA" || true
  fi
fi

if [[ -z "${NOTESTACK_DB_USER}" || -z "${NOTESTACK_DB_NAME}" || -z "${NOTESTACK_DB_PASSWORD}" ]]; then
  if notestack_url="$(_extract_database_url_from_env_file "${NOTESTACK_ENV_FILE}" 2>/dev/null)"; then
    _set_db_values_from_url "${notestack_url}" "NOTESTACK" || true
  fi
fi

if [[ -z "${PLEDGE_DB_USER}" || -z "${PLEDGE_DB_NAME}" || -z "${PLEDGE_DB_PASSWORD}" ]]; then
  if pledge_url="$(_extract_database_url_from_env_file "${PLEDGE_ENV_FILE}" 2>/dev/null)"; then
    _set_db_values_from_url "${pledge_url}" "PLEDGE" || true
  fi
fi

NOTESTACK_DB_NAME="${NOTESTACK_DB_NAME:-notestack_db}"
NOTESTACK_DB_USER="${NOTESTACK_DB_USER:-notestack_app}"
NOTESTACK_DB_PASSWORD="${NOTESTACK_DB_PASSWORD:-notestack_app_db_2026_prod_secret}"

if [[ -z "${NOTESTACK_DB_PASSWORD}" ]]; then
  echo "[setup-postgres] NoteStack PostgreSQL password is empty." >&2
  echo "[setup-postgres] Set DATABASE_URL in ${NOTESTACK_ENV_FILE} with credentials or pass NOTESTACK_DB_PASSWORD." >&2
  exit 1
fi

echo "[setup-postgres] NoteStack PostgreSQL provisioning enabled for ${NOTESTACK_DB_USER}@${NOTESTACK_DB_NAME}."

NEERA_DB_NAME="${NEERA_DB_NAME:-neera_db}"

sudo -u postgres psql \
  -v auth_db_user="${AUTH_DB_USER}" \
  -v auth_db_password="${AUTH_DB_PASSWORD}" \
  -v radio_db_user="${RADIO_DB_USER}" \
  -v radio_db_password="${RADIO_DB_PASSWORD}" \
  -v neera_db_user="${NEERA_DB_USER}" \
  -v neera_db_password="${NEERA_DB_PASSWORD}" \
  -v notestack_db_user="${NOTESTACK_DB_USER}" \
  -v notestack_db_password="${NOTESTACK_DB_PASSWORD}" \
  -v green_pledge_db_user="${PLEDGE_DB_USER}" \
  -v green_pledge_db_password="${PLEDGE_DB_PASSWORD}" \
  < "${USERS_SQL}"

sudo -u postgres psql \
  -v auth_db_name="${AUTH_DB_NAME}" \
  -v auth_db_user="${AUTH_DB_USER}" \
  -v radio_db_name="${RADIO_DB_NAME}" \
  -v radio_db_user="${RADIO_DB_USER}" \
  -v neera_db_name="${NEERA_DB_NAME}" \
  -v neera_db_user="${NEERA_DB_USER}" \
  -v notestack_db_name="${NOTESTACK_DB_NAME}" \
  -v notestack_db_user="${NOTESTACK_DB_USER}" \
  -v green_pledge_db_name="${PLEDGE_DB_NAME}" \
  -v green_pledge_db_user="${PLEDGE_DB_USER}" \
  < "${DBS_SQL}"

echo "PostgreSQL roles and databases are ready."
