#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./platform-infra/prod-debian/scripts/install-nginx.sh"
  exit 1
fi

install -m 0644 "${PROD_DEBIAN_DIR}/nginx/nightcraft.conf" /etc/nginx/sites-available/nightcraft.conf
ln -sfn /etc/nginx/sites-available/nightcraft.conf /etc/nginx/sites-enabled/nightcraft.conf

if [[ -L /etc/nginx/sites-enabled/default ]]; then
  rm -f /etc/nginx/sites-enabled/default
fi

nginx -t
systemctl reload nginx

echo "Nginx config installed and reloaded."
