#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_SRC_DIR="${PROD_DEBIAN_DIR}/env-examples"
ENV_TARGET_DIR="${ENV_TARGET_DIR:-/etc/nightcraft}"
OVERWRITE="${OVERWRITE:-0}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./platform-infra/prod-debian/scripts/install-env.sh" >&2
  exit 1
fi

if [[ "${1:-}" == "--overwrite" ]]; then
  OVERWRITE=1
fi

install -d -m 0755 "${ENV_TARGET_DIR}"

copy_env() {
  local src_file="$1"
  local target_file="$2"

  if [[ ! -f "${src_file}" ]]; then
    echo "Missing env source file: ${src_file}" >&2
    exit 1
  fi

  if [[ "${OVERWRITE}" -eq 1 ]]; then
    install -m 0640 "${src_file}" "${target_file}"
    sed -i 's/\r$//' "${target_file}"
    echo "updated: ${target_file}"
    return
  fi

  if [[ -f "${target_file}" ]]; then
    sed -i 's/\r$//' "${target_file}"
    echo "kept existing: ${target_file}"
  else
    install -m 0640 "${src_file}" "${target_file}"
    sed -i 's/\r$//' "${target_file}"
    echo "created: ${target_file}"
  fi
}

copy_env "${ENV_SRC_DIR}/app-landing.env" "${ENV_TARGET_DIR}/app-landing.env"
copy_env "${ENV_SRC_DIR}/service-auth.env" "${ENV_TARGET_DIR}/service-auth.env"
copy_env "${ENV_SRC_DIR}/app-radio.env" "${ENV_TARGET_DIR}/app-radio.env"
copy_env "${ENV_SRC_DIR}/app-curio.env" "${ENV_TARGET_DIR}/app-curio.env"
copy_env "${ENV_SRC_DIR}/app-seeksage.env" "${ENV_TARGET_DIR}/app-seeksage.env"
copy_env "${ENV_SRC_DIR}/app-admin.env" "${ENV_TARGET_DIR}/app-admin.env"
copy_env "${ENV_SRC_DIR}/app-game.env" "${ENV_TARGET_DIR}/app-game.env"
copy_env "${ENV_SRC_DIR}/app-note.env" "${ENV_TARGET_DIR}/app-note.env"

echo "Env install complete. Review files under ${ENV_TARGET_DIR}."
