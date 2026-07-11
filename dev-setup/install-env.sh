#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

ENV_TARGET_DIR="${ENV_DIR}"
rm -rf "${ENV_TARGET_DIR}"
ensure_dir "${ENV_TARGET_DIR}"

log "Installing dev environment files to ${ENV_TARGET_DIR}"

copy_env() {
  local target_file="$1"
  local src_file="${ENV_SRC_DIR}/${target_file##*/}"

  if [[ ! -f "${src_file}" ]]; then
    warn "No template found for ${target_file}, skipping"
    return
  fi

  install -m 0640 "${src_file}" "${target_file}"

  sed -i "s|\${NIGHTCRAFT_SHARED_DIR}|${SHARED_DIR}|g" "${target_file}"
  log "  created: ${target_file}"
}

copy_env "${ENV_TARGET_DIR}/service-auth.env"
copy_env "${ENV_TARGET_DIR}/app-landing.env"
copy_env "${ENV_TARGET_DIR}/app-radio.env"
copy_env "${ENV_TARGET_DIR}/app-neera.env"
copy_env "${ENV_TARGET_DIR}/app-seeksage.env"
copy_env "${ENV_TARGET_DIR}/app-admin.env"
copy_env "${ENV_TARGET_DIR}/app-game.env"
copy_env "${ENV_TARGET_DIR}/app-note.env"

log "Dev environment files installed at ${ENV_TARGET_DIR}"