#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

PROD_DEBIAN_DIR="${REPO_ROOT}/platform-infra/prod-debian"

USERS_SQL="${PROD_DEBIAN_DIR}/postgres/users-and-permissions.sql"
DBS_SQL="${PROD_DEBIAN_DIR}/postgres/create-dbs.sql"

require_file "${USERS_SQL}"
require_file "${DBS_SQL}"

log "Creating PostgreSQL users and databases"

docker_cmd exec -i nightcraft-postgres psql -U postgres \
  -v auth_db_user="auth_app" \
  -v auth_db_password="auth_app_db_2026_prod_secret" \
  -v radio_db_user="radio_app" \
  -v radio_db_password="radio_app_db_2026_prod_secret" \
  -v neera_db_user="neera_app" \
  -v neera_db_password="neera_app_db_2026_prod_secret" \
  -v seeksage_db_user="seeksage_app" \
  -v seeksage_db_password="seeksage_app_db_2026_prod_secret" \
  -v notestack_db_user="notestack_app" \
  -v notestack_db_password="notestack_app_db_2026_prod_secret" \
  -v green_pledge_db_user="green_pledge_app" \
  -v green_pledge_db_password="green_pledge_app_db_2026_prod_secret" \
  < "${USERS_SQL}"

docker_cmd exec -i nightcraft-postgres psql -U postgres \
  -v auth_db_name="auth_db" \
  -v auth_db_user="auth_app" \
  -v radio_db_name="radio_db" \
  -v radio_db_user="radio_app" \
  -v neera_db_name="neera_db" \
  -v neera_db_user="neera_app" \
  -v seeksage_db_name="seeksage_db" \
  -v seeksage_db_user="seeksage_app" \
  -v notestack_db_name="notestack_db" \
  -v notestack_db_user="notestack_app" \
  -v green_pledge_db_name="green_pledge_db" \
  -v green_pledge_db_user="green_pledge_app" \
  < "${DBS_SQL}"

log "PostgreSQL users and databases created"