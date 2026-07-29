#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COMPOSE=(
  docker compose
  --project-name drn-stack
  --project-directory "${REPO_ROOT}"
  --file "${REPO_ROOT}/compose.yaml"
)

if (( $# == 0 )); then
  echo "Usage: $0 <command> [arguments...]" >&2
  echo "Example: $0 ros2 service call /drn/control/takeoff std_srvs/srv/Trigger '{}'" >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || {
  echo "Docker CLI was not found. Install or start Docker Desktop." >&2
  exit 1
}

MSYS_NO_PATHCONV=1 "${COMPOSE[@]}" exec -T ros-viz bash -lc '
  set -Eeo pipefail
  source /opt/ros/humble/setup.bash
  source /opt/drn_ws/install/setup.bash
  set -u
  exec "$@"
' bash "$@"
