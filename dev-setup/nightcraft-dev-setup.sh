#!/usr/bin/env bash
# nightcraft-dev-setup.sh
# Single orchestrator for local Nightcraft development environment.
# Designed to be kept outside the repo's deployment path, mirroring the
# production server bootstrap pattern.
#
# Usage:
#   bash dev-setup/nightcraft-dev-setup.sh
#   bash dev-setup/nightcraft-dev-setup.sh --clean
#   bash dev-setup/nightcraft-dev-setup.sh --skip-deps --skip-seed

set -euo pipefail

# Check if we need to escalate to root for system package installation.
# This works in a real terminal where sudo prompts for password.
NEED_ROOT=0
if [[ "${EUID}" -ne 0 ]]; then
  NEED_ROOT=1
  for arg in "$@"; do
    if [[ "${arg}" == "--no-sudo" ]]; then
      NEED_ROOT=0
      break
    fi
  done
fi

if [[ "${NEED_ROOT}" -eq 1 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    # Re-execute with sudo (will prompt for password on a real terminal)
    exec sudo bash "$0" "$@"
  fi
  echo ""
  echo "  ERROR: Root privileges required for system package installation."
  echo "  Run with sudo or use --no-sudo to skip system package installs."
  echo ""
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

SKIP_INFRA=0
SKIP_DEPS=0
SKIP_SEED=0
NO_START=0
CLEAN=0

usage() {
  cat <<'EOF'
Usage:
  bash dev-setup/nightcraft-dev-setup.sh [options]

Setup a local Nightcraft development environment with Docker-based
PostgreSQL + Redis and venv-based Python services.

Options:
  --skip-infra    Skip Docker infra (postgres/redis) setup
  --skip-deps     Skip Python dependency installation
  --skip-seed     Skip database seeding (users + OAuth clients)
  --no-start      Skip starting services after setup
  --clean         Remove all .nightcraft-* state before starting
  -h, --help      Show this help
EOF
  exit 0
}

# --no-sudo is handled by the root-detection block above and must be stripped
# before the option parser runs.
_orch_args=()
for _a in "$@"; do
  if [[ "${_a}" != "--no-sudo" ]]; then
    _orch_args+=("${_a}")
  fi
done
set -- "${_orch_args[@]}"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --skip-infra) SKIP_INFRA=1 ;;
    --skip-deps)  SKIP_DEPS=1 ;;
    --skip-seed)  SKIP_SEED=1 ;;
    --no-start)   NO_START=1 ;;
    --clean)      CLEAN=1 ;;
    -h|--help)    usage ;;
    *) die "Unknown argument: $1" ;;
  esac
  shift
done

run_step() {
  local name="$1"
  local script="$2"
  shift 2

  log "--- Step: ${name} ---"
  if [[ -x "${script}" ]]; then
    "${script}" "$@"
  else
    bash "${script}" "$@"
  fi
  log "--- Step '${name}' complete ---"
}

main() {
  log "=== Nightcraft Dev Setup ==="
  log "Repo root: ${REPO_ROOT}"
  log "Log file:  ${LOG_FILE}"
  log "Env dir:   ${ENV_DIR}"
  log "Venv dir:  ${VENV_DIR}"
  log "Shared:    ${SHARED_DIR}"

  if [[ "${CLEAN}" -eq 1 ]]; then
    log "Cleaning previous state..."
    run_step "stop-all"       "${SCRIPT_DIR}/stop-all.sh"
    run_step "stop-infra"     "${SCRIPT_DIR}/stop-infra.sh"
    rm -rf "${ENV_DIR}" "${VENV_DIR}" "${SHARED_DIR}" "${REPO_ROOT}/.nightcraft-logs"
    log "Clean complete"
  fi

  ensure_dir "${LOG_DIR}"

  run_step "check-deps"      "${SCRIPT_DIR}/check-deps.sh"

  if [[ "${SKIP_INFRA}" -eq 0 ]]; then
    run_step "start-infra"   "${SCRIPT_DIR}/start-infra.sh"
    run_step "setup-dbs"     "${SCRIPT_DIR}/setup-dbs.sh"
  else
    log "Skipping infrastructure + database setup"
  fi

  run_step "install-env"     "${SCRIPT_DIR}/install-env.sh"

  if [[ "${SKIP_DEPS}" -eq 0 ]]; then
    run_step "install-deps"  "${SCRIPT_DIR}/install-deps.sh"
  else
    log "Skipping dependency installation"
  fi

  if [[ "${SKIP_SEED}" -eq 0 ]]; then
    run_step "seed-data"     "${SCRIPT_DIR}/seed-data.sh"
  else
    log "Skipping database seeding"
  fi

  if [[ "${NO_START}" -eq 0 ]]; then
    run_step "start-all"     "${SCRIPT_DIR}/start-all.sh"
  else
    log "Skipping service startup (--no-start)"
  fi

  log "=== Dev setup complete ==="
  echo ""
  echo "  Services running on:"
  echo "    http://127.0.0.1:5100/auth       (Auth service)"
  echo "    http://127.0.0.1:5333/devradio    (DevRadio)"
  echo "    http://127.0.0.1:5400            (Landing page)"
  echo "    http://127.0.0.1:5500/admin      (Admin panel)"
  echo "    http://127.0.0.1:5600/neera      (Neera)"
  echo "    http://127.0.0.1:5800/game       (Game)"
  echo "    http://127.0.0.1:5900/notestack  (NoteStack)"
  echo "    http://127.0.0.1:8000            (Mindmap)"
  echo ""
  echo "  Seed users: seeduser/seeduser123 (user), seedadmin/seedadmin123 (admin)"
  echo "  Dev user:   devuser/devpass123"
  echo ""
  echo "  To stop:   bash dev-setup/stop-all.sh && bash dev-setup/stop-infra.sh"
  echo "  To restart: bash dev-setup/nightcraft-dev-setup.sh"
}

main "$@"