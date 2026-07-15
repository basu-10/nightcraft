#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./deploy-all.sh" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

"${SCRIPT_DIR}/deploy-auth.sh"
"${SCRIPT_DIR}/deploy-radio.sh"
"${SCRIPT_DIR}/deploy-neera.sh"
"${SCRIPT_DIR}/deploy-landing.sh"
"${SCRIPT_DIR}/deploy-admin.sh"
"${SCRIPT_DIR}/deploy-game.sh"
"${SCRIPT_DIR}/deploy-note.sh"
"${SCRIPT_DIR}/deploy-pledge.sh"
"${SCRIPT_DIR}/deploy-tinyxl.sh"
"${SCRIPT_DIR}/seed-auth-users.sh"
"${SCRIPT_DIR}/seed-auth-client.sh"
"${SCRIPT_DIR}/seed-neera-client.sh"
"${SCRIPT_DIR}/seed-game-client.sh"
"${SCRIPT_DIR}/seed-pledge-client.sh"

# (a) Push the latest manifest so the manager picks up policy changes.
install -m 0644 "${PROD_DEBIAN_DIR}/products.yml" /etc/nightcraft/products.yml

# (b) Regenerate on-demand nginx blocks + loader.
"${SCRIPT_DIR}/gen-nginx-on-demand.sh"

# (c) Ensure the manager is running and reads the fresh manifest.
systemctl restart nightcraft-runtime-manager.service

# (d) Restart always_on products; leave on_demand stopped (manager starts them).
restart_list=()
while IFS= read -r slug; do
  [[ -z "${slug}" ]] && continue
  service="$(nc_service "${slug}")"
  if nc_is_on_demand "${slug}"; then
    log "Skipping start of on_demand ${service} (manager controls it)"
  else
    restart_list+=("${service}")
  fi
done < <(nc_slugs)

if [[ "${#restart_list[@]}" -gt 0 ]]; then
  systemctl restart "${restart_list[@]}"
fi

# (e) Reload nginx to pick up the regenerated include.
systemctl reload nginx

status_list=("${restart_list[@]}" nginx nightcraft-runtime-manager.service)
systemctl status --no-pager "${status_list[@]}" || true
