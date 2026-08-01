#!/usr/bin/env bash
set -Eeo pipefail

source /usr/local/bin/drn-ros-environment
set -u

agent_pid=""
ros_pid=""
project_pid=""

shutdown() {
  trap - TERM INT EXIT
  if [[ -n "${ros_pid}" ]] && kill -0 "${ros_pid}" 2>/dev/null; then
    kill -TERM "${ros_pid}" 2>/dev/null || true
  fi
  if [[ -n "${agent_pid}" ]] && kill -0 "${agent_pid}" 2>/dev/null; then
    kill -TERM "${agent_pid}" 2>/dev/null || true
  fi
  if [[ -n "${project_pid}" ]] && kill -0 "${project_pid}" 2>/dev/null; then
    kill -TERM "${project_pid}" 2>/dev/null || true
  fi
  wait "${ros_pid}" 2>/dev/null || true
  wait "${agent_pid}" 2>/dev/null || true
  wait "${project_pid}" 2>/dev/null || true
}
trap shutdown TERM INT EXIT

MicroXRCEAgent udp4 -p "${XRCE_PORT:-8888}" &
agent_pid=$!

ros2 launch drn_viz visualize.launch.py \
  "odometry_topic:=${ODOMETRY_TOPIC:-/fmu/out/vehicle_odometry}" \
  "foxglove_port:=${FOXGLOVE_PORT:-8765}" &
ros_pid=$!

if [[ -n "${DRN_PROJECT_MANIFEST:-}" ]]; then
  /usr/local/bin/drn-project launch "${DRN_PROJECT_MANIFEST}" &
  project_pid=$!
fi

processes=("${agent_pid}" "${ros_pid}")
if [[ -n "${project_pid}" ]]; then
  processes+=("${project_pid}")
fi

wait -n "${processes[@]}"
status=$?
exit "${status}"
