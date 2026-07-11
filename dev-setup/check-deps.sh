#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

NEED_SUDO=0
if [[ "${EUID}" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
  NEED_SUDO=1
fi

sudo_it() {
  if [[ "${NEED_SUDO}" -eq 1 ]]; then
    sudo "$@"
  else
    "$@"
  fi
}

APT_UPDATED=0
ensure_apt_updated() {
  if [[ "${APT_UPDATED}" -eq 0 ]]; then
    log "Running apt update..."
    sudo_it apt-get update -qq
    APT_UPDATED=1
  fi
}

install_pkgs() {
  ensure_apt_updated
  sudo_it apt-get install -y -qq "$@"
}

INSTALLED_ANY=0

log "Checking and installing required system dependencies"

if ! command -v python3 >/dev/null 2>&1; then
  log "Installing python3..."
  install_pkgs python3
  INSTALLED_ANY=1
fi

if ! python3 -c 'import venv' >/dev/null 2>&1; then
  log "Installing python3-venv..."
  install_pkgs python3-venv
  INSTALLED_ANY=1
fi

if ! command -v pip3 >/dev/null 2>&1; then
  if ! python3 -m pip --version >/dev/null 2>&1; then
    log "Installing python3-pip..."
    install_pkgs python3-pip
    INSTALLED_ANY=1
  fi
fi

if ! command -v pg_isready >/dev/null 2>&1; then
  log "Installing postgresql-client (for pg health checks)..."
  install_pkgs postgresql-client
  INSTALLED_ANY=1
fi

if ! command -v redis-cli >/dev/null 2>&1; then
  log "Installing redis-tools (for redis health checks)..."
  install_pkgs redis-tools
  INSTALLED_ANY=1
fi

if ! command -v npm >/dev/null 2>&1; then
  log "Installing Node.js and npm (needed for SeekSage frontend)..."
  if ! command -v node >/dev/null 2>&1; then
    install_pkgs nodejs npm
  else
    install_pkgs npm
  fi
  INSTALLED_ANY=1
fi

DOCKER_INSTALLED=0
if command -v docker >/dev/null 2>&1; then
  DOCKER_INSTALLED=1
fi

if [[ "${DOCKER_INSTALLED}" -eq 0 ]]; then
  log "Installing Docker from apt repositories..."
  ensure_apt_updated
  install_pkgs docker.io docker-compose-v2

  CURRENT_USER="${SUDO_USER:-${USER}}"
  if ! id -nG "${CURRENT_USER}" | grep -qw docker; then
    log "Adding ${CURRENT_USER} to docker group..."
    sudo_it usermod -aG docker "${CURRENT_USER}"
    log "WARN: User added to docker group. Log out and back in, or run: newgrp docker"
  fi

  sudo_it systemctl enable docker 2>/dev/null || true
  sudo_it systemctl start docker 2>/dev/null || true

  INSTALLED_ANY=1
  DOCKER_INSTALLED=1
fi

if command -v docker >/dev/null 2>&1; then
  if ! docker info >/dev/null 2>&1; then
    log "Docker daemon not accessible. Attempting with sudo..."
    if sudo docker info >/dev/null 2>&1; then
      log "Docker accessible via sudo"
    else
      log "Docker daemon not running. Attempting to start..."
      sudo_it systemctl start docker 2>/dev/null || true
      sleep 3
      for i in $(seq 1 10); do
        if sudo docker info >/dev/null 2>&1; then
          log "Docker daemon started"
          break
        fi
        sleep 2
      done
      if ! sudo docker info >/dev/null 2>&1; then
        die "Docker daemon failed to start. Try: sudo systemctl start docker"
      fi
    fi
  fi
else
  die "Docker installation failed — docker command not found"
fi

if [[ "${INSTALLED_ANY}" -eq 1 ]]; then
  log "All dependencies installed successfully"
else
  log "All dependencies already present"
fi