#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

# Always-required infrastructure.
sudo systemctl start redis-server.service

# Start always_on products; on_demand products are left stopped so the
# runtime manager brings them up on first request.
while IFS= read -r slug; do
  [[ -z "${slug}" ]] && continue
  service="$(nc_service "${slug}")"
  if nc_is_on_demand "${slug}"; then
    log "Skipping start of on_demand ${service} (manager controls it)"
  else
    sudo systemctl start "${service}"
  fi
done < <(nc_slugs)

# Runtime manager is itself always-on.
sudo systemctl start nightcraft-runtime-manager.service

status_list=()
while IFS= read -r slug; do
  [[ -z "${slug}" ]] && continue
  status_list+=("$(nc_service "${slug}")")
done < <(nc_slugs)

sudo systemctl status --no-pager "${status_list[@]}" nightcraft-runtime-manager.service
