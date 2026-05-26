#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

log "cleanup-releases.sh is obsolete in the direct-source deployment model"
log "No action needed because apps now run directly from /nightcraft-source-code source checkouts"
