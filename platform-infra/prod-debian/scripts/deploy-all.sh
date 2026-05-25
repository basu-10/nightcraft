#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./deploy-all.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/deploy-auth.sh"
"${SCRIPT_DIR}/deploy-radio.sh"
"${SCRIPT_DIR}/deploy-curio.sh"
"${SCRIPT_DIR}/deploy-seeksage.sh"
"${SCRIPT_DIR}/deploy-landing.sh"
"${SCRIPT_DIR}/deploy-admin.sh"
"${SCRIPT_DIR}/deploy-game.sh"
"${SCRIPT_DIR}/deploy-note.sh"
"${SCRIPT_DIR}/seed-auth-users.sh"
"${SCRIPT_DIR}/seed-auth-client.sh"
"${SCRIPT_DIR}/seed-curio-client.sh"
"${SCRIPT_DIR}/seed-seeksage-client.sh"
"${SCRIPT_DIR}/seed-game-client.sh"

systemctl restart nightcraft-auth.service
systemctl restart nightcraft-radio.service
systemctl restart nightcraft-curio.service
systemctl restart nightcraft-seeksage.service
systemctl restart nightcraft-landing.service
systemctl restart nightcraft-admin.service
systemctl restart nightcraft-game.service
systemctl restart nightcraft-note.service
systemctl reload nginx

systemctl status --no-pager nightcraft-auth.service nightcraft-radio.service nightcraft-curio.service nightcraft-seeksage.service nightcraft-landing.service nightcraft-admin.service nightcraft-game.service nightcraft-note.service nginx
