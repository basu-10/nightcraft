#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROD_DEBIAN_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_SRC_DIR="${PROD_DEBIAN_DIR}/env-examples"
ENV_TARGET_DIR="${ENV_TARGET_DIR:-/etc/nightcraft}"
OVERWRITE="${OVERWRITE:-0}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo ./nightcraft-source-code/platform-infra/prod-debian/scripts/install-env.sh" >&2
  exit 1
fi

if [[ "${1:-}" == "--overwrite" ]]; then
  OVERWRITE=1
fi

install -d -m 0755 "${ENV_TARGET_DIR}"

copy_env() {
  local target_file="$1"
  local required_flag="$2"
  shift 2

  local src_file=""
  local candidate

  for candidate in "$@"; do
    if [[ -f "${candidate}" ]]; then
      src_file="${candidate}"
      break
    fi
  done

  if [[ -z "${src_file}" ]]; then
    if [[ "${required_flag}" -eq 1 ]]; then
      echo "Missing required env source file candidates for ${target_file}" >&2
      exit 1
    fi

    if [[ -f "${target_file}" ]]; then
      sed -i 's/\r$//' "${target_file}"
      echo "kept existing (no source template found): ${target_file}"
    else
      echo "skipped optional env (no source template found): ${target_file}"
    fi
    return
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

copy_env "${ENV_TARGET_DIR}/app-landing.env" 1 \
  "${ENV_SRC_DIR}/app-landing.env" \
  "${ENV_SRC_DIR}/landing.env.example"
copy_env "${ENV_TARGET_DIR}/service-auth.env" 1 \
  "${ENV_SRC_DIR}/service-auth.env" \
  "${ENV_SRC_DIR}/auth.env.example"
copy_env "${ENV_TARGET_DIR}/app-radio.env" 1 \
  "${ENV_SRC_DIR}/app-radio.env" \
  "${ENV_SRC_DIR}/radio.env.example"
copy_env "${ENV_TARGET_DIR}/app-neera.env" 1 \
  "${ENV_SRC_DIR}/app-neera.env" \
  "${ENV_SRC_DIR}/neera.env.example"
copy_env "${ENV_TARGET_DIR}/app-seeksage.env" 1 \
  "${ENV_SRC_DIR}/app-seeksage.env" \
  "${ENV_SRC_DIR}/seeksage.env.example"
copy_env "${ENV_TARGET_DIR}/app-admin.env" 1 \
  "${ENV_SRC_DIR}/app-admin.env" \
  "${ENV_SRC_DIR}/admin.env.example"
copy_env "${ENV_TARGET_DIR}/app-game.env" 0 \
  "${ENV_SRC_DIR}/app-game.env"
copy_env "${ENV_TARGET_DIR}/app-note.env" 1 \
  "${ENV_SRC_DIR}/app-note.env" \
  "${ENV_SRC_DIR}/note.env.example"
copy_env "${ENV_TARGET_DIR}/app-pledge.env" 1 \
  "${ENV_SRC_DIR}/app-pledge.env" \
  "${ENV_SRC_DIR}/pledge.env.example"

echo "Env install complete. Review files under ${ENV_TARGET_DIR}."
