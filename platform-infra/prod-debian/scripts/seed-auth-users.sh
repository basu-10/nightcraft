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

AUTH_ROLE_USER_USERNAME="${AUTH_ROLE_USER_USERNAME:-seeduser}"
AUTH_ROLE_USER_EMAIL="${AUTH_ROLE_USER_EMAIL:-seeduser@example.com}"
AUTH_ROLE_USER_PASSWORD="${AUTH_ROLE_USER_PASSWORD:-seeduser123}"

AUTH_ROLE_ADMIN_USERNAME="${AUTH_ROLE_ADMIN_USERNAME:-seedadmin}"
AUTH_ROLE_ADMIN_EMAIL="${AUTH_ROLE_ADMIN_EMAIL:-seedadmin@example.com}"
AUTH_ROLE_ADMIN_PASSWORD="${AUTH_ROLE_ADMIN_PASSWORD:-seedadmin123}"

cd "${AUTH_SRC_DIR}"
"${AUTH_VENV_DIR}/bin/python" -m flask --app run.py seed-role-users \
  --user-username "${AUTH_ROLE_USER_USERNAME}" \
  --user-email "${AUTH_ROLE_USER_EMAIL}" \
  --user-password "${AUTH_ROLE_USER_PASSWORD}" \
  --admin-username "${AUTH_ROLE_ADMIN_USERNAME}" \
  --admin-email "${AUTH_ROLE_ADMIN_EMAIL}" \
  --admin-password "${AUTH_ROLE_ADMIN_PASSWORD}"

echo "Seed complete for auth role users: '${AUTH_ROLE_USER_USERNAME}' (user), '${AUTH_ROLE_ADMIN_USERNAME}' (admin)."