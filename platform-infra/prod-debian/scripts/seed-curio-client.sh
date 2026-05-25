#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_file "/etc/nightcraft/service-auth.env"

if [[ ! -d "${AUTH_SRC_DIR}" ]]; then
  echo "service-auth is not deployed. Run deploy-auth.sh first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source /etc/nightcraft/service-auth.env
set +a

CURIO_PUBLIC_URL="${CURIO_PUBLIC_URL:-http://31.70.85.89}"
CURIO_PUBLIC_PATH="${CURIO_PUBLIC_PATH:-/curio}"
AUTH_SEED_USERNAME="${AUTH_SEED_USERNAME:-devuser}"
AUTH_SEED_EMAIL="${AUTH_SEED_EMAIL:-devuser@example.com}"
AUTH_SEED_PASSWORD="${AUTH_SEED_PASSWORD:-devpass123}"
AUTH_SEED_CLIENT_ID="${AUTH_SEED_CLIENT_ID:-curio-app}"
AUTH_SEED_CLIENT_SECRET="${AUTH_SEED_CLIENT_SECRET:-curio-app-client-secret-2026}"

redirect_uri="${CURIO_PUBLIC_URL%/}${CURIO_PUBLIC_PATH}/auth/callback"

cd "${AUTH_SRC_DIR}"
"${AUTH_VENV_DIR}/bin/flask" --app run.py seed-dev \
  --username "${AUTH_SEED_USERNAME}" \
  --email "${AUTH_SEED_EMAIL}" \
  --password "${AUTH_SEED_PASSWORD}" \
  --client-id "${AUTH_SEED_CLIENT_ID}" \
  --client-secret "${AUTH_SEED_CLIENT_SECRET}" \
  --redirect-uri "${redirect_uri}"

echo "Seed complete for oauth client '${AUTH_SEED_CLIENT_ID}' redirect '${redirect_uri}'."
