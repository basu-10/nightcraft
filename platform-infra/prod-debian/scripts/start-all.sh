#!/usr/bin/env bash
set -euo pipefail

sudo systemctl start redis-server.service
sudo systemctl start nightcraft-auth.service
sudo systemctl start nightcraft-radio.service
sudo systemctl start nightcraft-neera.service
sudo systemctl start nightcraft-seeksage.service
sudo systemctl start nightcraft-landing.service
sudo systemctl start nightcraft-admin.service
sudo systemctl start nightcraft-game.service
sudo systemctl start nightcraft-note.service
sudo systemctl status --no-pager nightcraft-auth.service nightcraft-radio.service nightcraft-neera.service nightcraft-seeksage.service nightcraft-landing.service nightcraft-admin.service nightcraft-game.service nightcraft-note.service
