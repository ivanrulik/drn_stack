#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
BASE_IMAGE="drn-stack/ros-viz:humble"
PX4_IMAGE="drn-stack/px4-sitl:v1.17.0"

usage() {
  echo "Usage: $0 <project-directory> <scenario> [--evidence]" >&2
}

if (( $# < 2 || $# > 3 )); then
  usage
  exit 2
fi

project_input="$1"
scenario="$2"
evidence_argument="${3:-}"
if [[ -n "${evidence_argument}" && "${evidence_argument}" != "--evidence" ]]; then
  usage
  exit 2
fi
evidence_setting="${DRN_EVIDENCE:-0}"
if [[ ! "${evidence_setting}" =~ ^[01]$ ]]; then
  echo "DRN_EVIDENCE must be 0 or 1; got '${evidence_setting}'." >&2
  exit 2
fi
evidence_enabled="${evidence_setting}"
if [[ "${evidence_argument}" == "--evidence" ]]; then
  evidence_enabled=1
fi
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
recording_started=0
evidence_initialized=0
evidence_root=""
run_dir=""
run_id=""
started_at=""
project_name=""
ros_image="unavailable"
ros_image_id="unavailable"
px4_image_id="unavailable"
evidence_max_bytes="${DRN_EVIDENCE_MAX_BYTES:-1073741824}"
evidence_retention_count="${DRN_EVIDENCE_RETENTION_COUNT:-5}"

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

evidence_exec() {
  MSYS_NO_PATHCONV=1 project_compose exec -T ros-viz bash -lc '
    source /usr/local/bin/drn-ros-environment
    set -u
    exec /usr/local/bin/drn-evidence "$@"
  ' bash "$@"
}

evidence_run() {
  local mount_source="$1"
  local mount_target="$2"
  shift 2
  MSYS_NO_PATHCONV=1 docker run --rm \
    --mount "type=bind,src=${mount_source},dst=${mount_target}" \
    --entrypoint bash \
    "${BASE_IMAGE}" -lc '
      source /usr/local/bin/drn-ros-environment
      set -u
      exec /usr/local/bin/drn-evidence "$@"
    ' bash "$@"
}

cleanup() {
  local status=$?
  local verdict="failed"
  local finished_at=""
  local -a finalize_args=()
  trap - EXIT
  if (( stack_owned )); then
    if (( recording_started )); then
      if ! evidence_exec stop /opt/drn_artifacts; then
        echo "Evidence recorder did not finalize cleanly." >&2
        status=1
      fi
    fi
    if (( evidence_initialized )); then
      if ! project_compose logs --no-color --tail=500 >"${run_dir}/logs/compose.log" 2>&1; then
        echo "Could not capture bounded Compose logs." >&2
        status=1
      fi
    fi
    if (( ! succeeded )); then
      echo
      echo "Scenario failed. Recent project logs:"
      project_compose logs --no-color --tail=200 || true
    fi
    project_compose down --remove-orphans --timeout 30 || status=1
  fi
  if (( evidence_initialized )); then
    finished_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    if (( succeeded && status == 0 )); then
      verdict="passed"
    fi
    finalize_args=(
      finalize /evidence
      --run-id "${run_id}"
      --project "${project_name}"
      --scenario "${scenario}"
      --verdict "${verdict}"
      --started-at "${started_at}"
      --finished-at "${finished_at}"
      --git-revision "$(git -C "${REPO_ROOT}" rev-parse HEAD)"
      --ros-image "${ros_image}"
      --ros-image-id "${ros_image_id}"
      --px4-image "${PX4_IMAGE}"
      --px4-image-id "${px4_image_id}"
      --vehicle "${PX4_SIM_MODEL}"
      --world "${PX4_GZ_WORLD}"
      --ros-domain-id "${ROS_DOMAIN_ID:-0}"
      --max-pack-bytes "${evidence_max_bytes}"
    )
    if [[ "${verdict}" == "failed" ]]; then
      finalize_args+=(--error "scenario workflow exited with code ${status}")
    fi
    if ! evidence_run "${run_dir}" /evidence "${finalize_args[@]}"; then
      status=1
    fi
    if [[ -f "${run_dir}/manifest.json" ]] &&
      ! evidence_run "${run_dir}" /evidence validate /evidence; then
      status=1
    fi
    if ! evidence_run "${evidence_root}" /artifacts \
      prune /artifacts --keep "${evidence_retention_count}"; then
      status=1
    fi
    echo "Evidence pack: ${run_dir}"
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
project_name="$(project_tool get "${container_manifest}" name)"
PX4_SIM_MODEL="$(project_tool get "${container_manifest}" vehicle)"
PX4_GZ_WORLD="$(project_tool get "${container_manifest}" world)"
export PX4_SIM_MODEL PX4_GZ_WORLD

if (( evidence_enabled )); then
  if [[ ! "${evidence_max_bytes}" =~ ^[1-9][0-9]*$ ]]; then
    echo "DRN_EVIDENCE_MAX_BYTES must be a positive integer." >&2
    exit 2
  fi
  if [[ ! "${evidence_retention_count}" =~ ^[1-9][0-9]*$ ]] ||
    (( evidence_retention_count > 100 )); then
    echo "DRN_EVIDENCE_RETENTION_COUNT must be an integer from 1 to 100." >&2
    exit 2
  fi
  evidence_root_input="${DRN_EVIDENCE_ROOT:-${REPO_ROOT}/artifacts}"
  mkdir -p "${evidence_root_input}"
  evidence_root="$(cd -- "${evidence_root_input}" && pwd)"
  run_id="$(date -u +%Y%m%dT%H%M%SZ)-${scenario}-$(git -C "${REPO_ROOT}" rev-parse --short=8 HEAD)"
  run_dir="${evidence_root}/${run_id}"
  if [[ -e "${run_dir}" ]]; then
    echo "Evidence run directory already exists: ${run_dir}" >&2
    exit 1
  fi
  mkdir -p "${run_dir}/logs" "${run_dir}/metadata" "${run_dir}/ulog"
  cp "${manifest_path}" "${run_dir}/metadata/project.yaml"
  cp "${scenario_path}" "${run_dir}/metadata/scenario.yaml"
  cp "${REPO_ROOT}/compose.yaml" "${run_dir}/metadata/compose.yaml"
  export DRN_ARTIFACT_DIR="${run_dir}"
  PROJECT_COMPOSE+=(--file "${REPO_ROOT}/compose.evidence.yaml")
  started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  evidence_initialized=1
fi

project_compose config --quiet
echo "Building project overlay for ${PROJECT_ROOT}..."
base_compose build px4-sitl
project_compose build ros-viz
ros_image="drn-stack/${project_name}:humble"
ros_image_id="$(docker image inspect --format '{{.Id}}' "${ros_image}")"
px4_image_id="$(docker image inspect --format '{{.Id}}' "${PX4_IMAGE}")"

stack_owned=1
project_compose up -d --no-build --remove-orphans --wait --wait-timeout 300
if (( evidence_enabled )); then
  evidence_exec start /opt/drn_artifacts "${container_manifest}"
  recording_started=1
fi
if (( evidence_enabled )); then
  MSYS_NO_PATHCONV=1 project_compose exec -T ros-viz bash -lc '
    source /usr/local/bin/drn-ros-environment
    set -u
    exec "$@"
  ' bash /usr/local/bin/drn-project run \
    "${container_manifest}" "${container_scenario}" 2>&1 |
    tee "${run_dir}/logs/scenario.log"
else
  MSYS_NO_PATHCONV=1 project_compose exec -T ros-viz bash -lc '
    source /usr/local/bin/drn-ros-environment
    set -u
    exec "$@"
  ' bash /usr/local/bin/drn-project run "${container_manifest}" "${container_scenario}"
fi
succeeded=1
echo "Scenario '${scenario}' passed; stopping the isolated stack."
