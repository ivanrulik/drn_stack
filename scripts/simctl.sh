#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COMPOSE=(docker compose --project-name drn-stack --project-directory "${REPO_ROOT}" -f "${REPO_ROOT}/compose.yaml")
export COMPOSE_PARALLEL_LIMIT="${COMPOSE_PARALLEL_LIMIT:-1}"

compose() {
  "${COMPOSE[@]}" "$@"
}

require_docker() {
  command -v docker >/dev/null 2>&1 || {
    echo "Docker CLI was not found. Install or start Docker Desktop." >&2
    exit 1
  }
  docker compose version >/dev/null 2>&1 || {
    echo "Docker Compose v2 is required." >&2
    exit 1
  }
  docker info >/dev/null 2>&1 || {
    echo "Docker Desktop is not running or its Linux daemon is unavailable." >&2
    exit 1
  }
  if [[ "$(docker context show)" != "desktop-linux" ]] && [[ "$(docker info --format '{{.OSType}}')" != "linux" ]]; then
    echo "The DRN stack requires Docker's Linux container engine." >&2
    exit 1
  fi
}

storage_status() {
  local available_kib available_gib
  available_kib="$(df -Pk "${REPO_ROOT}" | awk 'NR == 2 {print $4}')"
  if [[ ! "${available_kib}" =~ ^[0-9]+$ ]]; then
    echo "Could not determine free host space for ${REPO_ROOT}." >&2
    exit 1
  fi
  available_gib="$(awk -v kib="${available_kib}" 'BEGIN {printf "%.1f", kib / 1048576}')"
  echo "Host storage: ${available_gib} GiB free on the filesystem containing the repository."
}

check_storage() {
  local minimum_gib="${DRN_MIN_HOST_FREE_GB:-50}"
  local available_kib minimum_kib
  if [[ ! "${minimum_gib}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "DRN_MIN_HOST_FREE_GB must be a non-negative number; got '${minimum_gib}'." >&2
    exit 2
  fi

  available_kib="$(df -Pk "${REPO_ROOT}" | awk 'NR == 2 {print $4}')"
  minimum_kib="$(awk -v gib="${minimum_gib}" 'BEGIN {printf "%.0f", gib * 1048576}')"
  storage_status
  if (( available_kib < minimum_kib )); then
    echo "Refusing to start with less than ${minimum_gib} GiB free." >&2
    echo "Free host space or set DRN_MIN_HOST_FREE_GB only when the override is intentional." >&2
    exit 1
  fi
}

check_port_conflicts() {
  local port owner
  for port in "${FOXGLOVE_PORT:-8765}" "${QGC_PORT:-14550}"; do
    owner="$(docker ps --filter "publish=${port}" --format '{{.Names}}' | grep -v '^drn-stack-' || true)"
    if [[ -n "${owner}" ]]; then
      echo "Port ${port} is already published by Docker container: ${owner}" >&2
      exit 1
    fi
  done
}

dump_failure() {
  echo
  echo "DRN stack did not become ready. Current state:"
  compose ps || true
  echo
  echo "Recent logs:"
  compose logs --tail=100 || true
}

print_summary() {
  compose ps
  echo
  echo "DRN simulation is ready."
  echo "Foxglove: ws://localhost:${FOXGLOVE_PORT:-8765}"
  echo "QGroundControl: UDP localhost:${QGC_PORT:-14550}"
  echo "Logs: ./scripts/logs.sh"
  echo "Status: ./scripts/status.sh"
  echo "Stop: ./scripts/stop.sh"
}

smoke_full() {
  MSYS_NO_PATHCONV=1 compose exec -T ros-viz /usr/local/bin/drn-smoke-test full
}

smoke_quick() {
  MSYS_NO_PATHCONV=1 compose exec -T ros-viz /usr/local/bin/drn-smoke-test quick
}

run_stack() {
  require_docker
  check_storage
  check_port_conflicts
  compose config --quiet
  if ! compose build ros-viz || ! compose build px4-sitl; then
    dump_failure
    exit 1
  fi
  if ! compose up -d --no-build --remove-orphans --wait --wait-timeout 300; then
    dump_failure
    exit 1
  fi
  if ! smoke_full; then
    dump_failure
    exit 1
  fi
  print_summary
}

stop_stack() {
  if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "DRN simulation is already stopped (Docker engine is unavailable)."
    return 0
  fi
  compose down --remove-orphans --timeout 30
}

restart_stack() {
  require_docker
  check_storage
  compose stop --timeout 30
  if ! compose up -d --no-build --remove-orphans --wait --wait-timeout 300; then
    dump_failure
    exit 1
  fi
  if ! smoke_full; then
    dump_failure
    exit 1
  fi
  print_summary
}

status_stack() {
  require_docker
  storage_status
  compose ps
  smoke_quick
  echo
  echo "Foxglove and PX4 odometry checks passed."
}

logs_stack() {
  require_docker
  local service="${1:-}"
  case "${service}" in
    "")
      compose logs --follow --tail=200
      ;;
    px4-sitl|ros-viz)
      compose logs --follow --tail=200 "${service}"
      ;;
    *)
      echo "Unknown service '${service}'. Use px4-sitl or ros-viz." >&2
      exit 2
      ;;
  esac
}

clean_stack() {
  require_docker
  if [[ "${1:-}" != "--yes" ]]; then
    echo "Refusing cleanup without --yes." >&2
    echo "This removes only drn-stack containers, volumes, and locally built images." >&2
    exit 2
  fi
  compose down --remove-orphans --volumes --rmi local --timeout 30
}

action="${1:-}"
shift || true

case "${action}" in
  run) run_stack "$@" ;;
  stop) stop_stack "$@" ;;
  restart) restart_stack "$@" ;;
  status) status_stack "$@" ;;
  logs) logs_stack "$@" ;;
  clean) clean_stack "$@" ;;
  smoke) require_docker; smoke_full ;;
  *)
    echo "Usage: $0 {run|stop|restart|status|logs|clean|smoke}" >&2
    exit 2
    ;;
esac
