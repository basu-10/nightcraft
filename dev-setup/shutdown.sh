#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

log "Shutting down Nightcraft dev environment"

log "Step 1: Stopping app services..."
"${SCRIPT_DIR}/stop-all.sh"

log "Step 2: Stopping infrastructure containers..."
"${SCRIPT_DIR}/stop-infra.sh"

echo ""
echo "  Nightcraft dev environment stopped."
echo "  To restart: bash dev-setup/nightcraft-dev-setup.sh"
echo "  To wipe and rebuild: bash dev-setup/nightcraft-dev-setup.sh --clean"
echo ""