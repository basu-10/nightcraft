#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

log "Starting infrastructure containers (PostgreSQL + Redis)"

cd "${SCRIPT_DIR}"

docker_compose_cmd pull -q 2>/dev/null || true
docker_compose_cmd up -d --wait --remove-orphans

log "Infrastructure containers are running"
wait_for_pg
wait_for_redis
log "PostgreSQL and Redis ready"