#!/usr/bin/env bash
set -euo pipefail

sudo systemctl restart nightcraft-auth.service
sudo systemctl restart nightcraft-radio.service
sudo systemctl restart nightcraft-neera.service
sudo systemctl restart nightcraft-seeksage.service
sudo systemctl restart nightcraft-landing.service
sudo systemctl restart nightcraft-admin.service
sudo systemctl restart nightcraft-game.service
sudo systemctl restart nightcraft-note.service
sudo systemctl restart nightcraft-tinyxl.service
sudo systemctl reload nginx
sudo systemctl status --no-pager nightcraft-auth.service nightcraft-radio.service nightcraft-neera.service nightcraft-seeksage.service nightcraft-landing.service nightcraft-admin.service nightcraft-game.service nightcraft-note.service nightcraft-tinyxl.service nginx
