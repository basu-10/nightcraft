#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./nightcraft-source-code/platform-infra/prod-debian/scripts/install-systemd.sh"
  exit 1
fi

install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-auth.service" /etc/systemd/system/nightcraft-auth.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-radio.service" /etc/systemd/system/nightcraft-radio.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-neera.service" /etc/systemd/system/nightcraft-neera.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-seeksage.service" /etc/systemd/system/nightcraft-seeksage.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-landing.service" /etc/systemd/system/nightcraft-landing.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-admin.service" /etc/systemd/system/nightcraft-admin.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-game.service" /etc/systemd/system/nightcraft-game.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-note.service" /etc/systemd/system/nightcraft-note.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-pledge.service" /etc/systemd/system/nightcraft-pledge.service
install -m 0644 "${PROD_DEBIAN_DIR}/systemd/nightcraft-tinyxl.service" /etc/systemd/system/nightcraft-tinyxl.service

systemctl daemon-reload
systemctl enable nightcraft-auth.service
systemctl enable nightcraft-radio.service
systemctl enable nightcraft-neera.service
systemctl enable nightcraft-seeksage.service
systemctl enable nightcraft-landing.service
systemctl enable nightcraft-admin.service
systemctl enable nightcraft-game.service
systemctl enable nightcraft-note.service
systemctl enable nightcraft-pledge.service
systemctl enable nightcraft-tinyxl.service

echo "Systemd units installed and enabled."
