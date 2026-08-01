#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BASE_IMAGE="drn-stack/ros-viz:humble"

usage() {
  echo "Usage: $0 <project-directory> <scenario>" >&2
}

if (( $# != 2 )); then
  usage
  exit 2
fi

project_input="$1"
scenario="$2"
if [[ ! "${scenario}" =~ ^[a-z][a-z0-9]*(-[a-z0-9]+)*$ ]]; then
  echo "Scenario must be a lowercase hyphenated name; got '${scenario}'." >&2
  exit 2
fi
if [[ ! -d "${project_input}" ]]; then
  echo "Project directory was not found: ${project_input}" >&2
  exit 2
fi

PROJECT_ROOT="$(cd -- "${project_input}" && pwd)"
manifest_path="${PROJECT_ROOT}/project.yaml"
override_path="${PROJECT_ROOT}/compose.override.yaml"
scenario_path="${PROJECT_ROOT}/scenarios/${scenario}.yaml"
for required_path in "${manifest_path}" "${override_path}" "${scenario_path}"; do
  if [[ ! -f "${required_path}" ]]; then
    echo "Required project file was not found: ${required_path}" >&2
    exit 2
  fi
done

BASE_COMPOSE=(
  docker compose
  --project-name drn-stack
  --project-directory "${REPO_ROOT}"
  --file "${REPO_ROOT}/compose.yaml"
)
PROJECT_COMPOSE=("${BASE_COMPOSE[@]}" --file "${override_path}")
project_mount="type=bind,src=${PROJECT_ROOT},dst=/opt/drn_project,readonly"
container_manifest="/opt/drn_project/project.yaml"
container_scenario="/opt/drn_project/scenarios/${scenario}.yaml"
stack_owned=0
succeeded=0

base_compose() {
  "${BASE_COMPOSE[@]}" "$@"
}

project_compose() {
  "${PROJECT_COMPOSE[@]}" "$@"
}

project_tool() {
  MSYS_NO_PATHCONV=1 docker run --rm \
    --mount "${project_mount}" \
    --entrypoint /usr/local/bin/drn-project \
    "${BASE_IMAGE}" "$@"
}

cleanup() {
  local status=$?
  trap - EXIT
  if (( stack_owned )); then
    if (( ! succeeded )); then
      echo
      echo "Scenario failed. Recent project logs:"
      project_compose logs --no-color --tail=200 || true
    fi
    project_compose down --remove-orphans --timeout 30 || status=1
  fi
  exit "${status}"
}
trap cleanup EXIT

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
if [[ "$(docker info --format '{{.OSType}}')" != "linux" ]]; then
  echo "The DRN stack requires Docker's Linux container engine." >&2
  exit 1
fi

minimum_gib="${DRN_MIN_HOST_FREE_GB:-50}"
if [[ ! "${minimum_gib}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
  echo "DRN_MIN_HOST_FREE_GB must be a non-negative number; got '${minimum_gib}'." >&2
  exit 2
fi
available_kib="$(df -Pk "${REPO_ROOT}" | awk 'NR == 2 {print $4}')"
minimum_kib="$(awk -v gib="${minimum_gib}" 'BEGIN {printf "%.0f", gib * 1048576}')"
available_gib="$(awk -v kib="${available_kib}" 'BEGIN {printf "%.1f", kib / 1048576}')"
echo "Host storage: ${available_gib} GiB free on the filesystem containing the repository."
if (( available_kib < minimum_kib )); then
  echo "Refusing to start with less than ${minimum_gib} GiB free." >&2
  exit 1
fi

for port in "${FOXGLOVE_PORT:-8765}" "${QGC_PORT:-14550}"; do
  owners="$(docker ps --filter "publish=${port}" --format '{{.Names}}' | grep -v '^drn-stack-' || true)"
  if [[ -n "${owners}" ]]; then
    echo "Port ${port} is already published by Docker container: ${owners}" >&2
    exit 1
  fi
done

if [[ -n "$(base_compose ps --all --quiet)" ]]; then
  echo "The drn-stack Compose project is already running. Stop it before running an isolated scenario." >&2
  exit 1
fi

echo "Building the pinned DRN base image..."
base_compose build ros-viz
project_tool validate "${container_manifest}" "${container_scenario}"

export DRN_PROJECT_DIR="${PROJECT_ROOT}"
PX4_SIM_MODEL="$(project_tool get "${container_manifest}" vehicle)"
PX4_GZ_WORLD="$(project_tool get "${container_manifest}" world)"
export PX4_SIM_MODEL PX4_GZ_WORLD

project_compose config --quiet
echo "Building project overlay for ${PROJECT_ROOT}..."
base_compose build px4-sitl
project_compose build ros-viz

stack_owned=1
project_compose up -d --no-build --remove-orphans --wait --wait-timeout 300
MSYS_NO_PATHCONV=1 project_compose exec -T ros-viz bash -lc '
  source /usr/local/bin/drn-ros-environment
  set -u
  exec "$@"
' bash /usr/local/bin/drn-project run "${container_manifest}" "${container_scenario}"
succeeded=1
echo "Scenario '${scenario}' passed; stopping the isolated stack."
