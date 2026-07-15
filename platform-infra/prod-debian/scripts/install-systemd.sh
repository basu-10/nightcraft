#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_DIR="${PROD_DEBIAN_DIR}/systemd"
MANAGER_SRC="${PROD_DEBIAN_DIR}/runtime-manager/nightcraft-runtime-manager.py"
MANAGER_INSTALL_DIR="/opt/nightcraft/runtime-manager"
MANAGER_STATE_DIR="/runtime/nightcraft/manager"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./nightcraft-source-code/platform-infra/prod-debian/scripts/install-systemd.sh"
  exit 1
fi

# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_cmd python3
nc_ensure_yaml

ensure_dir /etc/nightcraft
ensure_dir /etc/systemd/system/nightcraft-pledge.service.d

# 1. Install the manifest (source of truth for runtime policy).
install -m 0644 "${PROD_DEBIAN_DIR}/products.yml" /etc/nightcraft/products.yml
log "Installed /etc/nightcraft/products.yml"

# 2. Install + (conditionally) enable every product service from the manifest.
while IFS= read -r slug; do
  [[ -z "${slug}" ]] && continue
  service="$(nc_service "${slug}")"
  policy="$(nc_policy "${slug}")"

  install -m 0644 "${SYSTEMD_DIR}/${service}" "/etc/systemd/system/${service}"
  log "Installed ${service} (${policy})"

  if [[ "${policy}" == "on_demand" ]]; then
    # Override Restart=always so the manager's idle `systemctl stop` sticks.
    dropin_dir="/etc/systemd/system/${service}.d"
    ensure_dir "${dropin_dir}"
    cat > "${dropin_dir}/nightcraft-on-demand.conf" <<'EOF'
[Service]
Restart=no
EOF
    # Ensure it is NOT enabled (so it stays down until first request). Idempotent:
    # does not stop a currently-running service, just removes the boot enable.
    systemctl disable "${service}" >/dev/null 2>&1 || true
    log "  -> on_demand: installed Restart=no drop-in + disabled (manager controls it)"
  else
    systemctl enable "${service}"
    # Remove any stale on_demand drop-in so a reverted product auto-restarts.
    rm -f "/etc/systemd/system/${service}.d/nightcraft-on-demand.conf"
    log "  -> always_on: enabled"
  fi
done < <(nc_slugs)

# 3. Radio ingest (separate timer, not a manifest product) — unchanged.
install -m 0644 "${SYSTEMD_DIR}/nightcraft-radio-ingest.service" /etc/systemd/system/nightcraft-radio-ingest.service
install -m 0644 "${SYSTEMD_DIR}/nightcraft-radio-ingest.timer" /etc/systemd/system/nightcraft-radio-ingest.timer
systemctl enable nightcraft-radio-ingest.timer
log "Installed + enabled nightcraft-radio-ingest.timer"

# 4. Runtime Manager (always-on, root, Restart=always).
ensure_dir "${MANAGER_INSTALL_DIR}"
ensure_dir "${MANAGER_STATE_DIR}"
install -m 0755 "${MANAGER_SRC}" "${MANAGER_INSTALL_DIR}/nightcraft-runtime-manager.py"
install -m 0644 "${SYSTEMD_DIR}/nightcraft-runtime-manager.service" /etc/systemd/system/nightcraft-runtime-manager.service

# Drop-ins must exist before the final daemon-reload.
systemctl daemon-reload
systemctl enable --now nightcraft-runtime-manager.service
log "Installed + started nightcraft-runtime-manager.service"

echo "Systemd units installed."
