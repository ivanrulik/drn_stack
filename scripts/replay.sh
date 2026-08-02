#!/usr/bin/env bash
set -Eeuo pipefail

BASE_IMAGE="drn-stack/ros-viz:humble"

usage() {
  echo "Usage: $0 <evidence-directory> [ROS-image]" >&2
}

if (( $# < 1 || $# > 2 )); then
  usage
  exit 2
fi
if [[ ! -d "$1" ]]; then
  echo "Evidence directory was not found: $1" >&2
  exit 2
fi

EVIDENCE_DIR="$(cd -- "$1" && pwd)"
image="${2:-${DRN_REPLAY_IMAGE:-${BASE_IMAGE}}}"
port="${FOXGLOVE_PORT:-8765}"
if [[ ! "${port}" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
  echo "FOXGLOVE_PORT must be an integer from 1 to 65535." >&2
  exit 2
fi

command -v docker >/dev/null 2>&1 || {
  echo "Docker CLI was not found. Install or start Docker Desktop." >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo "Docker Desktop is not running or its Linux daemon is unavailable." >&2
  exit 1
}
docker image inspect "${image}" >/dev/null 2>&1 || {
  echo "Replay image was not found: ${image}" >&2
  echo "Run an evidence-enabled scenario first, or pass its project image." >&2
  exit 1
}
owners="$(docker ps --filter "publish=${port}" --format '{{.Names}}')"
if [[ -n "${owners}" ]]; then
  echo "Port ${port} is already published by Docker container: ${owners}" >&2
  exit 1
fi

echo "Open Foxglove at ws://localhost:${port}; replay exits when the bag ends."
MSYS_NO_PATHCONV=1 docker run --rm --init \
  --publish "127.0.0.1:${port}:${port}/tcp" \
  --mount "type=bind,src=${EVIDENCE_DIR},dst=/evidence,readonly" \
  --entrypoint bash \
  "${image}" -lc '
    source /usr/local/bin/drn-ros-environment
    set -u
    exec /usr/local/bin/drn-evidence "$@"
  ' bash replay /evidence --port "${port}"
