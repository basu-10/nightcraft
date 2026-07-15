#!/usr/bin/env bash
set -uo pipefail

sudo systemctl status --no-pager nightcraft-auth.service nightcraft-radio.service nightcraft-neera.service nightcraft-landing.service nightcraft-admin.service nightcraft-game.service nightcraft-note.service nightcraft-pledge.service nightcraft-tinyxl.service nginx postgresql redis-server|| true
