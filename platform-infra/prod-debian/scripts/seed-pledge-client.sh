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

# Load runtime env so DATABASE_URL/OIDC vars are aligned with systemd.
set -a
# shellcheck disable=SC1091
source /etc/nightcraft/service-auth.env
set +a

PLEDGE_PUBLIC_URL="${PLEDGE_PUBLIC_URL:-http://31.70.85.89}"
PLEDGE_PUBLIC_PATH="${PLEDGE_PUBLIC_PATH:-/green-pledge}"
AUTH_SEED_USERNAME="${AUTH_SEED_USERNAME:-devuser}"
AUTH_SEED_EMAIL="${AUTH_SEED_EMAIL:-devuser@example.com}"
AUTH_SEED_PASSWORD="${AUTH_SEED_PASSWORD:-devpass123}"
AUTH_SEED_CLIENT_ID="${AUTH_SEED_CLIENT_ID:-green-pledge-app}"
AUTH_SEED_CLIENT_SECRET="${AUTH_SEED_CLIENT_SECRET:-green-pledge-app-client-secret-2026}"

# Register callback URIs for every public path the app is served under so SSO
# login works regardless of which prefix a visitor uses. The auth service keeps
# redirect URIs additive, so seeding both is safe.
PLEDGE_PUBLIC_PATHS=("/green-pledge" "/pledge")

cd "${AUTH_SRC_DIR}"
for pledge_path in "${PLEDGE_PUBLIC_PATHS[@]}"; do
  redirect_uri="${PLEDGE_PUBLIC_URL%/}${pledge_path}/auth/callback"
  "${AUTH_VENV_DIR}/bin/python" -m flask --app run.py seed-dev \
    --username "${AUTH_SEED_USERNAME}" \
    --email "${AUTH_SEED_EMAIL}" \
    --password "${AUTH_SEED_PASSWORD}" \
    --client-id "${AUTH_SEED_CLIENT_ID}" \
    --client-secret "${AUTH_SEED_CLIENT_SECRET}" \
    --redirect-uri "${redirect_uri}"
  echo "Seeded oauth client '${AUTH_SEED_CLIENT_ID}' redirect '${redirect_uri}'."
done

echo "Seed complete for oauth client '${AUTH_SEED_CLIENT_ID}'."
