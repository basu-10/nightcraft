#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./platform-infra/prod-debian/scripts/reset-stack.sh --yes [options]" >&2
  exit 1
fi

WITH_POSTGRES=0
WITH_ENV=0
WITH_SYSTEMD=0
WITH_NGINX=0
REMOVE_SHARED_DATA=0
CONFIRMED=0

usage() {
  cat <<'EOF'
Usage:
  reset-stack.sh --yes [--remove-shared-data] [--with-postgres] [--with-env] [--with-systemd] [--with-nginx]

Default behavior (with only --yes):
  - stop stack services
  - keep /platform-infra source checkouts intact
  - keep /platform-infra/runtime/shared/* data directories
  - delete /platform-infra/runtime/venvs virtualenv directories for those apps

Optional destructive flags:
  --remove-shared-data Remove /platform-infra/runtime/shared/* data directories too
  --with-postgres   Drop auth/radio databases and roles (using env defaults/overrides)
  --with-env        Remove /etc/nightcraft/*.env files used by this stack
  --with-systemd    Disable and remove nightcraft-*.service unit files
  --with-nginx      Remove nginx nightcraft site config/symlink and reload nginx

Notes:
  - This script is destructive by design.
  - Run setup-host.sh/setup-postgres.sh/install-systemd.sh/install-nginx.sh/deploy-all.sh afterwards.
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --yes)
      CONFIRMED=1
      ;;
    --with-postgres)
      WITH_POSTGRES=1
      ;;
    --remove-shared-data)
      REMOVE_SHARED_DATA=1
      ;;
    --with-env)
      WITH_ENV=1
      ;;
    --with-systemd)
      WITH_SYSTEMD=1
      ;;
    --with-nginx)
      WITH_NGINX=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

if [[ "${CONFIRMED}" -ne 1 ]]; then
  echo "Refusing to run without --yes" >&2
  usage
  exit 1
fi

SERVICES=(
  nightcraft-auth.service
  nightcraft-radio.service
  nightcraft-curio.service
  nightcraft-seeksage.service
  nightcraft-landing.service
  nightcraft-admin.service
  nightcraft-game.service
  nightcraft-note.service
)

log "Stopping stack services"
for svc in "${SERVICES[@]}"; do
  systemctl stop "${svc}" >/dev/null 2>&1 || true
done

if [[ "${REMOVE_SHARED_DATA}" -eq 1 ]]; then
  log "Removing runtime shared data directories"
  rm -rf "${AUTH_SHARED_DIR}" "${RADIO_SHARED_DIR}" "${CURIO_SHARED_DIR}" "${SEEKSAGE_SHARED_DIR}" "${LANDING_SHARED_DIR}" "${ADMIN_SHARED_DIR}" "${GAME_SHARED_DIR}" "${NOTE_SHARED_DIR}"
else
  log "Keeping runtime shared data directories under ${SHARED_ROOT}"
fi

log "Removing virtualenv trees"
rm -rf "${AUTH_VENV_DIR}" "${RADIO_VENV_DIR}" "${CURIO_VENV_DIR}" "${SEEKSAGE_VENV_DIR}" "${LANDING_VENV_DIR}" "${ADMIN_VENV_DIR}" "${NOTE_VENV_DIR}"

if [[ "${WITH_ENV}" -eq 1 ]]; then
  log "Removing env files under /etc/nightcraft"
  rm -f \
    /etc/nightcraft/service-auth.env \
    /etc/nightcraft/app-radio.env \
    /etc/nightcraft/app-curio.env \
    /etc/nightcraft/app-seeksage.env \
    /etc/nightcraft/app-landing.env \
    /etc/nightcraft/app-admin.env \
    /etc/nightcraft/app-note.env
fi

if [[ "${WITH_SYSTEMD}" -eq 1 ]]; then
  log "Disabling and removing systemd unit files"
  for svc in "${SERVICES[@]}"; do
    systemctl disable "${svc}" >/dev/null 2>&1 || true
  done

  rm -f \
    /etc/systemd/system/nightcraft-auth.service \
    /etc/systemd/system/nightcraft-radio.service \
    /etc/systemd/system/nightcraft-curio.service \
    /etc/systemd/system/nightcraft-seeksage.service \
    /etc/systemd/system/nightcraft-landing.service \
    /etc/systemd/system/nightcraft-admin.service \
    /etc/systemd/system/nightcraft-game.service \
    /etc/systemd/system/nightcraft-note.service

  systemctl daemon-reload
fi

if [[ "${WITH_NGINX}" -eq 1 ]]; then
  log "Removing nginx nightcraft site config"
  rm -f /etc/nginx/sites-enabled/nightcraft.conf
  rm -f /etc/nginx/sites-available/nightcraft.conf

  if nginx -t >/dev/null 2>&1; then
    systemctl reload nginx || true
  else
    log "nginx config test failed after cleanup; check nginx manually"
  fi
fi

if [[ "${WITH_POSTGRES}" -eq 1 ]]; then
  AUTH_DB_NAME="${AUTH_DB_NAME:-auth_db}"
  AUTH_DB_USER="${AUTH_DB_USER:-auth_app}"
  RADIO_DB_NAME="${RADIO_DB_NAME:-radio_db}"
  RADIO_DB_USER="${RADIO_DB_USER:-radio_app}"

  log "Dropping postgres databases/roles: ${AUTH_DB_NAME}, ${RADIO_DB_NAME}, ${AUTH_DB_USER}, ${RADIO_DB_USER}"

  sudo -u postgres psql -v ON_ERROR_STOP=1 \
    -v auth_db_name="${AUTH_DB_NAME}" \
    -v radio_db_name="${RADIO_DB_NAME}" <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'auth_db_name'
  AND pid <> pg_backend_pid();

SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = :'radio_db_name'
  AND pid <> pg_backend_pid();

SELECT format('DROP DATABASE IF EXISTS %I', :'auth_db_name') \gexec
SELECT format('DROP DATABASE IF EXISTS %I', :'radio_db_name') \gexec
SQL

  sudo -u postgres psql -v ON_ERROR_STOP=1 \
    -v auth_db_user="${AUTH_DB_USER}" \
    -v radio_db_user="${RADIO_DB_USER}" <<'SQL'
SELECT format('DROP ROLE IF EXISTS %I', :'auth_db_user') \gexec
SELECT format('DROP ROLE IF EXISTS %I', :'radio_db_user') \gexec
SQL
fi

log "Reset complete. Next steps (from repo root):"
log "  sudo platform-infra/prod-debian/scripts/setup-host.sh"
log "  sudo platform-infra/prod-debian/scripts/setup-postgres.sh"
log "  sudo platform-infra/prod-debian/scripts/install-systemd.sh"
log "  sudo platform-infra/prod-debian/scripts/install-nginx.sh"
log "  platform-infra/prod-debian/scripts/deploy-all.sh"
