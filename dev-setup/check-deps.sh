#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

# On a dev laptop we must NOT pollute the host OS with apt installs. Docker
# provides PostgreSQL + Redis, and uv provides isolated Python environments.
# Set NIGHTCRAFT_INSTALL_APT=1 to allow apt-based installation (e.g. on a bare
# server that is being bootstrapped for the first time).
ALLOW_APT="${NIGHTCRAFT_INSTALL_APT:-0}"

sudo_it() {
  if [[ "${ALLOW_APT}" -eq 1 ]] && [[ "${EUID}" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    "$@"
  fi
}

APT_UPDATED=0
ensure_apt_updated() {
  if [[ "${ALLOW_APT}" -ne 1 ]]; then
    return 0
  fi
  if [[ "${APT_UPDATED}" -eq 0 ]]; then
    log "Running apt update..."
    sudo_it apt-get update -qq
    APT_UPDATED=1
  fi
}

install_pkgs() {
  if [[ "${ALLOW_APT}" -ne 1 ]]; then
    warn "Skipping apt install of: $* (set NIGHTCRAFT_INSTALL_APT=1 to allow)"
    return 0
  fi
  ensure_apt_updated
  sudo_it apt-get install -y -qq "$@"
}

log "Checking required tooling"

missing=0
need_cmd() {
  local cmd="$1"
  local pkg="$2"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    if [[ "${ALLOW_APT}" -eq 1 ]]; then
      install_pkgs "${pkg}"
    else
      warn "Required command not found: ${cmd} (install via ${pkg}, or set NIGHTCRAFT_INSTALL_APT=1)"
      missing=1
    fi
  fi
}

need_cmd python3 python3
need_cmd uv "uv (https://docs.astral.sh/uv)"
need_cmd node nodejs
need_cmd npm npm
# postgresql-client / redis-tools are intentionally NOT required: the health
# checks in common.sh run pg_isready/redis-cli INSIDE the Docker containers.

if [[ "${missing}" -eq 1 ]]; then
  die "Missing required tooling. Install it or set NIGHTCRAFT_INSTALL_APT=1"
fi

# Docker is required (provides PostgreSQL + Redis in isolated containers).
if ! command -v docker >/dev/null 2>&1; then
  if [[ "${ALLOW_APT}" -eq 1 ]]; then
    log "Installing Docker from apt repositories..."
    ensure_apt_updated
    install_pkgs docker.io docker-compose-v2
  else
    die "Docker not found. Install Docker, or set NIGHTCRAFT_INSTALL_APT=1"
  fi
fi

if command -v docker >/dev/null 2>&1; then
  if ! docker info >/dev/null 2>&1; then
    log "Docker daemon not accessible. Attempting to start..."
    sudo_it systemctl start docker 2>/dev/null || true
    sleep 3
    for i in $(seq 1 10); do
      if sudo_it docker info >/dev/null 2>&1; then
        log "Docker daemon started"
        break
      fi
      sleep 2
    done
    if ! sudo_it docker info >/dev/null 2>&1; then
      die "Docker daemon failed to start. Try: sudo systemctl start docker"
    fi
  fi
else
  die "Docker installation failed — docker command not found"
fi

log "All required tooling present (apt installs skipped: NIGHTCRAFT_INSTALL_APT=${ALLOW_APT})"
