#!/usr/bin/env bash
# Idempotent 2 GB swap creation for the DevRadio VPS.
# Run once as root: sudo bash platform-infra/prod-debian/scripts/ensure-swap.sh
# A swap file gives the box headroom so a transient memory spike (e.g. an
# ingestion run) pages instead of thrashing kswapd0 and freezing everything.
set -euo pipefail

SWAPFILE="${SWAPFILE:-/swapfile}"
SWAPSIZE_GB="${SWAPSIZE_GB:-2}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This script must be run as root." >&2
  exit 1
fi

if swapon --show=NAME --noheadings | grep -qxF "${SWAPFILE}"; then
  echo "Swap already active at ${SWAPFILE}; nothing to do."
  exit 0
fi

if [[ -f "${SWAPFILE}" ]]; then
  echo "Swap file ${SWAPFILE} already exists; (re)activating."
else
  echo "Allocating ${SWAPSIZE_GB}G swap at ${SWAPFILE}..."
  if command -v fallocate >/dev/null 2>&1; then
    fallocate -l "${SWAPSIZE_GB}G" "${SWAPFILE}" || dd if=/dev/zero of="${SWAPFILE}" bs=1M count=$(( SWAPSIZE_GB * 1024 )) status=progress
  else
    dd if=/dev/zero of="${SWAPFILE}" bs=1M count=$(( SWAPSIZE_GB * 1024 )) status=progress
  fi
fi

chmod 600 "${SWAPFILE}"
mkswap "${SWAPFILE}"
swapon "${SWAPFILE}"

# Idempotently add an fstab entry so swap survives reboots.
FSTAB_LINE="${SWAPFILE} none swap sw 0 0"
if ! grep -qxF "${FSTAB_LINE}" /etc/fstab; then
  echo "Adding swap to /etc/fstab"
  echo "${FSTAB_LINE}" >> /etc/fstab
else
  echo "fstab entry already present."
fi

echo "Swap enabled. Current state:"
free -h
swapon --show
