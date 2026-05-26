#!/usr/bin/env bash
set -uo pipefail

sudo systemctl status --no-pager nightcraft-auth.service nightcraft-radio.service nightcraft-curio.service nightcraft-seeksage.service nightcraft-landing.service nightcraft-admin.service nightcraft-game.service nightcraft-note.service nginx postgresql || true
