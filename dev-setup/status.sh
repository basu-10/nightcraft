#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

SERVICES=(
  "auth:5100:service-auth"
  "radio:5333:app-radio"
  "landing:5400:app-landing"
  "admin:5500:app-admin"
  "neera:5600:app-neera"
  "game:5800:app-game"
  "note:5900:app-note"
  "mindmap:8000:app-mindmap"
)

echo ""
echo "=== Nightcraft Dev Status ==="
echo ""

echo "--- App Services ---"
for entry in "${SERVICES[@]}"; do
  name="${entry%%:*}"
  rest="${entry#*:}"
  port="${rest%%:*}"
  slug="${rest##*:}"

  pid_file="${SHARED_DIR}/${name}.pid"
  pid=""
  running="no"

  if [[ -f "${pid_file}" ]]; then
    pid=$(cat "${pid_file}" 2>/dev/null || echo "")
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      running="yes"
    fi
  fi

  if [[ "${running}" == "no" ]]; then
    if command -v ss >/dev/null 2>&1; then
      if ss -tln "sport = :${port}" 2>/dev/null | grep -q ":${port}[[:space:]]"; then
        running="port-in-use"
      fi
    fi
  fi

  case "${running}" in
    yes)
      echo "  [RUNNING] ${name} (PID ${pid}, port ${port}) — ${slug}"
      ;;
    port-in-use)
      echo "  [PORT USED] ${name} (port ${port}) — ${slug} (another process on port)"
      ;;
    *)
      echo "  [STOPPED] ${name} (port ${port}) — ${slug}"
      ;;
  esac
done

echo ""
echo "--- Infrastructure (Docker) ---"
CONTAINERS=("nightcraft-postgres" "nightcraft-redis")
for cname in "${CONTAINERS[@]}"; do
  status=$(docker_cmd inspect --format '{{.State.Status}}' "${cname}" 2>/dev/null || echo "not-found")
  if [[ "${status}" == "running" ]]; then
    port_info=$(docker_cmd inspect --format '{{range $p, $conf := .NetworkSettings.Ports}}{{$p}} -> {{(index $conf 0).HostPort}}{{"\n"}}{{end}}' "${cname}" 2>/dev/null | tr '\n' ' ' || echo "")
    echo "  [RUNNING] ${cname} — ${port_info}"
  elif [[ "${status}" == "not-found" ]]; then
    echo "  [MISSING] ${cname} — container does not exist"
  else
    echo "  [${status^^}] ${cname}"
  fi
done

echo ""
echo "--- Runtime Directories ---"
for d in "${ENV_DIR}" "${VENV_DIR}" "${SHARED_DIR}"; do
  if [[ -d "${d}" ]]; then
    size=$(du -sh "${d}" 2>/dev/null | cut -f1)
    echo "  ${d} (${size})"
  else
    echo "  ${d} (missing)"
  fi
done

echo ""