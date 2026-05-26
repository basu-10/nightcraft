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

CURIO_DB_NAME="${CURIO_DB_NAME:-}"
CURIO_DB_USER="${CURIO_DB_USER:-}"
CURIO_DB_PASSWORD="${CURIO_DB_PASSWORD:-}"

SEEKSAGE_DB_NAME="${SEEKSAGE_DB_NAME:-}"
SEEKSAGE_DB_USER="${SEEKSAGE_DB_USER:-}"
SEEKSAGE_DB_PASSWORD="${SEEKSAGE_DB_PASSWORD:-}"

NOTESTACK_DB_ENABLED="${NOTESTACK_DB_ENABLED:-}"
NOTESTACK_DB_NAME="${NOTESTACK_DB_NAME:-}"
NOTESTACK_DB_USER="${NOTESTACK_DB_USER:-}"
NOTESTACK_DB_PASSWORD="${NOTESTACK_DB_PASSWORD:-}"

CURIO_ENV_FILE="${CURIO_ENV_FILE:-/etc/nightcraft/app-curio.env}"
SEEKSAGE_ENV_FILE="${SEEKSAGE_ENV_FILE:-/etc/nightcraft/app-seeksage.env}"
NOTESTACK_ENV_FILE="${NOTESTACK_ENV_FILE:-/etc/nightcraft/app-note.env}"

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
  _extract_env_value_from_file "${env_file}" "DATABASE_URL"
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

if [[ -z "${CURIO_DB_USER}" || -z "${CURIO_DB_NAME}" || -z "${CURIO_DB_PASSWORD}" ]]; then
  if curio_url="$(_extract_database_url_from_env_file "${CURIO_ENV_FILE}")"; then
    _set_db_values_from_url "${curio_url}" "CURIO" || true
  fi
fi

if [[ -z "${SEEKSAGE_DB_USER}" || -z "${SEEKSAGE_DB_NAME}" || -z "${SEEKSAGE_DB_PASSWORD}" ]]; then
  if seeksage_url="$(_extract_database_url_from_env_file "${SEEKSAGE_ENV_FILE}")"; then
    _set_db_values_from_url "${seeksage_url}" "SEEKSAGE" || true
  fi
fi

if [[ -z "${NOTESTACK_DB_ENABLED}" ]]; then
  if notestack_backend="$(_extract_env_value_from_file "${NOTESTACK_ENV_FILE}" "NOTESTACK_DB_BACKEND" 2>/dev/null)"; then
    notestack_backend="$(printf '%s' "${notestack_backend}" | tr '[:upper:]' '[:lower:]' | xargs)"
    if [[ "${notestack_backend}" == "postgres" ]]; then
      NOTESTACK_DB_ENABLED="1"
    else
      NOTESTACK_DB_ENABLED="0"
    fi
  else
    NOTESTACK_DB_ENABLED="0"
  fi
fi

if [[ "${NOTESTACK_DB_ENABLED}" == "1" ]]; then
  if [[ -z "${NOTESTACK_DB_USER}" || -z "${NOTESTACK_DB_NAME}" || -z "${NOTESTACK_DB_PASSWORD}" ]]; then
    if notestack_url="$(_extract_database_url_from_env_file "${NOTESTACK_ENV_FILE}" 2>/dev/null)"; then
      _set_db_values_from_url "${notestack_url}" "NOTESTACK" || true
    fi
  fi

  NOTESTACK_DB_NAME="${NOTESTACK_DB_NAME:-notestack_db}"
  NOTESTACK_DB_USER="${NOTESTACK_DB_USER:-notestack_app}"
  NOTESTACK_DB_PASSWORD="${NOTESTACK_DB_PASSWORD:-notestack_app_db_2026_prod_secret}"

  if [[ -z "${NOTESTACK_DB_PASSWORD}" ]]; then
    echo "[setup-postgres] NoteStack postgres mode is enabled but NOTESTACK_DB_PASSWORD is empty." >&2
    echo "[setup-postgres] Set DATABASE_URL in ${NOTESTACK_ENV_FILE} with credentials or pass NOTESTACK_DB_PASSWORD." >&2
    exit 1
  fi

  echo "[setup-postgres] NoteStack postgres provisioning enabled for ${NOTESTACK_DB_USER}@${NOTESTACK_DB_NAME}."
else
  echo "[setup-postgres] NoteStack postgres provisioning skipped (NOTESTACK_DB_BACKEND is not postgres)."
fi

CURIO_DB_NAME="${CURIO_DB_NAME:-curio_db}"
CURIO_DB_USER="${CURIO_DB_USER:-curio_app}"
CURIO_DB_PASSWORD="${CURIO_DB_PASSWORD:-curio_app_db_2026_prod_secret}"

SEEKSAGE_DB_NAME="${SEEKSAGE_DB_NAME:-seeksage_db}"
SEEKSAGE_DB_USER="${SEEKSAGE_DB_USER:-seeksage_app}"
SEEKSAGE_DB_PASSWORD="${SEEKSAGE_DB_PASSWORD:-seeksage_app_db_2026_prod_secret}"

sudo -u postgres psql \
  -v auth_db_user="${AUTH_DB_USER}" \
  -v auth_db_password="${AUTH_DB_PASSWORD}" \
  -v radio_db_user="${RADIO_DB_USER}" \
  -v radio_db_password="${RADIO_DB_PASSWORD}" \
  -v curio_db_user="${CURIO_DB_USER}" \
  -v curio_db_password="${CURIO_DB_PASSWORD}" \
  -v seeksage_db_user="${SEEKSAGE_DB_USER}" \
  -v seeksage_db_password="${SEEKSAGE_DB_PASSWORD}" \
  -v notestack_db_enabled="${NOTESTACK_DB_ENABLED}" \
  -v notestack_db_user="${NOTESTACK_DB_USER}" \
  -v notestack_db_password="${NOTESTACK_DB_PASSWORD}" \
  < "${USERS_SQL}"

sudo -u postgres psql \
  -v auth_db_name="${AUTH_DB_NAME}" \
  -v auth_db_user="${AUTH_DB_USER}" \
  -v radio_db_name="${RADIO_DB_NAME}" \
  -v radio_db_user="${RADIO_DB_USER}" \
  -v curio_db_name="${CURIO_DB_NAME}" \
  -v curio_db_user="${CURIO_DB_USER}" \
  -v seeksage_db_name="${SEEKSAGE_DB_NAME}" \
  -v seeksage_db_user="${SEEKSAGE_DB_USER}" \
  -v notestack_db_enabled="${NOTESTACK_DB_ENABLED}" \
  -v notestack_db_name="${NOTESTACK_DB_NAME}" \
  -v notestack_db_user="${NOTESTACK_DB_USER}" \
  < "${DBS_SQL}"

echo "PostgreSQL roles and databases are ready."
