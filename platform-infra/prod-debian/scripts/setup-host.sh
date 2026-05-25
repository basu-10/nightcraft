#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./platform-infra/prod-debian/scripts/setup-host.sh"
  exit 1
fi

APP_USER="${APP_USER:-dev}"
APP_GROUP="${APP_GROUP:-${APP_USER}}"
INFRA_ROOT="${INFRA_ROOT:-/platform-infra}"
SHARED_ROOT="${SHARED_ROOT:-${INFRA_ROOT}/runtime/shared}"
VENV_ROOT="${VENV_ROOT:-${INFRA_ROOT}/runtime/venvs}"

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  python3 \
  python3-venv \
  python3-dev \
  build-essential \
  nodejs \
  npm \
  nginx \
  postgresql \
  postgresql-contrib \
  libpq-dev \
  rsync \
  curl \
  jq

install -d -m 0755 /etc/nightcraft
install -d -m 0755 "${INFRA_ROOT}"
install -d -m 0755 "${INFRA_ROOT}/runtime"
install -d -m 0755 "${SHARED_ROOT}"
install -d -m 0755 "${VENV_ROOT}"

if id -u "${APP_USER}" >/dev/null 2>&1; then
  chown -R "${APP_USER}:${APP_GROUP}" "${SHARED_ROOT}"
  chown -R "${APP_USER}:${APP_GROUP}" "${VENV_ROOT}"
else
  echo "Warning: user '${APP_USER}' does not exist. Create it first or set APP_USER." >&2
fi

systemctl enable nginx
systemctl enable postgresql

echo "Host setup complete."
