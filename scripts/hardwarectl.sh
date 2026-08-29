#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
action="${1:-}"
shift || true
profile="x500-basic"
bind_address="${DRN_HARDWARE_BIND_ADDRESS:-}"

while (( $# > 0 )); do
  case "$1" in
    --bind-address) bind_address="${2:-}"; shift 2 ;;
    --profile) profile="${2:-}"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ ! "${profile}" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "Invalid profile name '${profile}'." >&2
  exit 2
fi

if [[ ! "${bind_address}" =~ ^([0-9]{1,3}[.]){3}[0-9]{1,3}$ ]] ||
   [[ "${bind_address}" == "0.0.0.0" ]] || [[ "${bind_address}" == 127.* ]]; then
  echo "Set --bind-address (or DRN_HARDWARE_BIND_ADDRESS) to the explicit" >&2
  echo "non-loopback IPv4 address of the trusted bench interface." >&2
  exit 2
fi
IFS=. read -r -a octets <<<"${bind_address}"
for octet in "${octets[@]}"; do
  if (( 10#${octet} > 255 )); then
    echo "Invalid IPv4 bind address: ${bind_address}" >&2
    exit 2
  fi
done

profile_compose="${REPO_ROOT}/profiles/${profile}/compose.yaml"
if [[ ! -f "${profile_compose}" ]]; then
  echo "Unknown profile '${profile}'." >&2
  exit 2
fi

require_docker() {
  command -v docker >/dev/null 2>&1 || {
    echo "Docker CLI was not found." >&2
    exit 1
  }
  docker compose version >/dev/null 2>&1 || {
    echo "Docker Compose v2 is required." >&2
    exit 1
  }
  docker info >/dev/null 2>&1 || {
    echo "Docker's Linux daemon is unavailable." >&2
    exit 1
  }
  if [[ "$(docker info --format '{{.OSType}}')" != "linux" ]]; then
    echo "The DRN stack requires Linux containers." >&2
    exit 1
  fi
}

storage_check() {
  local available_kib minimum_kib minimum_gib="${DRN_MIN_HOST_FREE_GB:-50}"
  available_kib="$(df -Pk "${REPO_ROOT}" | awk 'NR == 2 {print $4}')"
  minimum_kib="$(awk -v gib="${minimum_gib}" 'BEGIN {printf "%.0f", gib * 1048576}')"
  if (( available_kib < minimum_kib )); then
    echo "Refusing to start with less than ${minimum_gib} GiB free." >&2
    exit 1
  fi
}

check_ports() {
  local port owner
  local ports=(
    "${FOXGLOVE_PORT:-8765}"
    "${XRCE_PORT:-8888}"
    "${DRN_HARDWARE_MAVLINK_PORT:-14580}"
  )
  for port in "${ports[@]}"; do
    owner="$(
      docker ps --filter "publish=${port}" --format '{{.Names}}' |
        grep -v '^drn-stack-' || true
    )"
    if [[ -n "${owner}" ]]; then
      echo "Port ${port} is already published by Docker container: ${owner}" >&2
      exit 1
    fi
  done
}

export DRN_HARDWARE_BIND_ADDRESS="${bind_address}"
export DRN_HARDWARE_ARTIFACTS="${REPO_ROOT}/artifacts/hardware"
DRN_GIT_REVISION="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
export DRN_GIT_REVISION
if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
  export DRN_GIT_DIRTY=true
else
  export DRN_GIT_DIRTY=false
fi
if docker image inspect drn-stack/ros-viz:humble >/dev/null 2>&1; then
  DRN_IMAGE_ID="$(docker image inspect drn-stack/ros-viz:humble --format '{{.Id}}')"
  export DRN_IMAGE_ID
fi
mkdir -p "${DRN_HARDWARE_ARTIFACTS}"
COMPOSE=(
  docker compose
  --project-name drn-stack
  --project-directory "${REPO_ROOT}"
  -f "${REPO_ROOT}/compose.yaml"
  -f "${profile_compose}"
  -f "${REPO_ROOT}/connections/hardware-udp/compose.yaml"
)
compose() { "${COMPOSE[@]}" "$@"; }
smoke() {
  MSYS_NO_PATHCONV=1 compose exec -T ros-viz /usr/local/bin/drn-hardware-smoke
}

require_docker
case "${action}" in
  run)
    storage_check; check_ports; compose config --quiet; compose build ros-viz
    DRN_IMAGE_ID="$(docker image inspect drn-stack/ros-viz:humble --format '{{.Id}}')"
    export DRN_IMAGE_ID
    compose up -d --no-build --remove-orphans --wait --wait-timeout 300 ros-viz
    smoke
    compose ps
    echo "DRN hardware UDP companion is ready (read-only, disarmed acceptance passed)."
    echo "Trusted interface: ${bind_address}; reports: artifacts/hardware"
    ;;
  restart)
    storage_check; compose stop --timeout 30 ros-viz
    compose up -d --no-build --remove-orphans --wait --wait-timeout 300 ros-viz
    smoke
    ;;
  status) compose ps; smoke ;;
  smoke) smoke ;;
  logs) compose logs --follow --tail=200 ros-viz ;;
  stop) compose down --remove-orphans --timeout 30 ;;
  *)
    echo "Usage: $0 {run|stop|restart|status|logs|smoke}" >&2
    echo "  --bind-address IPV4 [--profile NAME]" >&2
    exit 2
    ;;
esac
