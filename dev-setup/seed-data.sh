#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

log "Seeding auth users and OAuth clients"

if [[ ! -d "${AUTH_SRC_DIR}" ]]; then
  die "service-auth source not found at ${AUTH_SRC_DIR}"
fi

cd "${AUTH_SRC_DIR}"

AUTH_ENV="${ENV_DIR}/service-auth.env"
require_file "${AUTH_ENV}"

export NIGHTCRAFT_SHARED_DIR="${SHARED_DIR}"

set -a
source "${AUTH_ENV}"
set +a

seed_ok=0
seed_fail=0

safe_seed() {
  local label="$1"
  shift
  log "Seeding ${label}..."
  if "${AUTH_VENV}/bin/python" -m flask --app run.py "$@" 2>&1; then
    seed_ok=$((seed_ok + 1))
    log "  ${label} OK"
  else
    seed_fail=$((seed_fail + 1))
    warn "  ${label} skipped or already present"
  fi
}

safe_seed "role users (seeduser + seedadmin)" seed-role-users \
  --user-username "seeduser" \
  --user-email "seeduser@example.com" \
  --user-password "seeduser123" \
  --admin-username "seedadmin" \
  --admin-email "seedadmin@example.com" \
  --admin-password "seedadmin123"

safe_seed "OAuth client: radio-app" seed-dev \
  --username "devuser" \
  --email "devuser@example.com" \
  --password "devpass123" \
  --client-id "radio-app" \
  --client-secret "radio-app-client-secret-2026" \
  --redirect-uri "http://127.0.0.1:5333/devradio/auth/callback"

safe_seed "OAuth client: neera-app" seed-dev \
  --username "devuser" \
  --email "devuser@example.com" \
  --password "devpass123" \
  --client-id "neera-app" \
  --client-secret "neera-app-client-secret-2026" \
  --redirect-uri "http://127.0.0.1:5600/neera/auth/callback"

safe_seed "OAuth client: seeksage-app" seed-dev \
  --username "devuser" \
  --email "devuser@example.com" \
  --password "devpass123" \
  --client-id "seeksage-app" \
  --client-secret "seeksage-app-client-secret-2026" \
  --redirect-uri "http://127.0.0.1:5000/seeksage/auth/sso/callback"

safe_seed "OAuth client: game-app" seed-dev \
  --username "devuser" \
  --email "devuser@example.com" \
  --password "devpass123" \
  --client-id "game-app" \
  --client-secret "game-app-client-secret-2026" \
  --redirect-uri "http://127.0.0.1:5800/game/auth/callback"

log "Seed complete (${seed_ok} succeeded, ${seed_fail} skipped)"