#!/usr/bin/env bash
set -euo pipefail

DEPLOY_HISTORY_FILE="${DEPLOY_HISTORY_FILE:-/platform-infra/deploy-history.csv}"
RECENT_LIMIT="${RECENT_LIMIT:-5}"

usage() {
  cat <<'EOF'
Usage:
  status-deploys.sh [--history-file PATH] [--limit N]

Options:
  --history-file PATH   CSV file to read (default: /platform-infra/deploy-history.csv)
  --limit N             Number of recent deployments to show (default: 5)
  -h, --help            Show this help text
EOF
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --history-file)
      DEPLOY_HISTORY_FILE="${2:-}"
      shift
      ;;
    --limit)
      RECENT_LIMIT="${2:-}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

if [[ ! -f "${DEPLOY_HISTORY_FILE}" ]]; then
  echo "No deployment history found at ${DEPLOY_HISTORY_FILE}"
  exit 0
fi

mapfile -t history_lines < <(tail -n +2 "${DEPLOY_HISTORY_FILE}" | sed '/^$/d')

if [[ "${#history_lines[@]}" -eq 0 ]]; then
  echo "No deployment history entries found in ${DEPLOY_HISTORY_FILE}"
  exit 0
fi

format_time() {
  local raw_time="$1"
  printf '%s' "${raw_time}" | cut -c1-16
}

last_index=$(( ${#history_lines[@]} - 1 ))
IFS=',' read -r last_time last_branch last_commit last_duration last_status last_logfile <<< "${history_lines[${last_index}]}"

echo "Last deployment:"
echo "Commit: ${last_commit}"
echo "Time: $(format_time "${last_time}")"
echo "Duration: ${last_duration}s"
echo "Status: ${last_status}"
echo
echo "Recent deployments:"

start_index=$(( ${#history_lines[@]} - RECENT_LIMIT ))
if [[ "${start_index}" -lt 0 ]]; then
  start_index=0
fi

for ((i=start_index; i<${#history_lines[@]}; i++)); do
  IFS=',' read -r entry_time entry_branch entry_commit entry_duration entry_status entry_logfile <<< "${history_lines[$i]}"
  printf '%s | %s | %ss | %s\n' "$(format_time "${entry_time}")" "${entry_commit}" "${entry_duration}" "${entry_status}"
done