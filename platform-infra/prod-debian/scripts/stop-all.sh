#!/usr/bin/env bash
set -euo pipefail

sudo systemctl stop nightcraft-admin.service
sudo systemctl stop nightcraft-game.service
sudo systemctl stop redis-server.service
sudo systemctl stop nightcraft-note.service
sudo systemctl stop nightcraft-pledge.service
sudo systemctl stop nightcraft-tinyxl.service
sudo systemctl stop nightcraft-landing.service
sudo systemctl status --no-pager nightcraft-auth.service nightcraft-radio.service nightcraft-neera.service nightcraft-landing.service nightcraft-admin.service nightcraft-game.service nightcraft-note.service nightcraft-pledge.service nightcraft-tinyxl.service
