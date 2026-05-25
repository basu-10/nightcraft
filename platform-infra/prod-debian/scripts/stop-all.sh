#!/usr/bin/env bash
set -euo pipefail

sudo systemctl stop nightcraft-admin.service
sudo systemctl stop nightcraft-game.service
sudo systemctl stop nightcraft-note.service
sudo systemctl stop nightcraft-landing.service
sudo systemctl stop nightcraft-seeksage.service
sudo systemctl stop nightcraft-curio.service
sudo systemctl stop nightcraft-radio.service
sudo systemctl stop nightcraft-auth.service
sudo systemctl status --no-pager nightcraft-auth.service nightcraft-radio.service nightcraft-curio.service nightcraft-seeksage.service nightcraft-landing.service nightcraft-admin.service nightcraft-game.service nightcraft-note.service
