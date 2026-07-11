#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

log "Stopping infrastructure containers"

cd "${SCRIPT_DIR}"
docker_compose_cmd down

log "Infrastructure containers stopped"