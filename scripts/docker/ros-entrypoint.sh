#!/usr/bin/env bash
set -Eeo pipefail

source /opt/ros/humble/setup.bash
source /opt/drn_ws/install/setup.bash
set -u

agent_pid=""
ros_pid=""

shutdown() {
  trap - TERM INT EXIT
  if [[ -n "${ros_pid}" ]] && kill -0 "${ros_pid}" 2>/dev/null; then
    kill -TERM "${ros_pid}" 2>/dev/null || true
  fi
  if [[ -n "${agent_pid}" ]] && kill -0 "${agent_pid}" 2>/dev/null; then
    kill -TERM "${agent_pid}" 2>/dev/null || true
  fi
  wait "${ros_pid}" 2>/dev/null || true
  wait "${agent_pid}" 2>/dev/null || true
}
trap shutdown TERM INT EXIT

MicroXRCEAgent udp4 -p "${XRCE_PORT:-8888}" &
agent_pid=$!

ros2 launch drn_viz visualize.launch.py \
  "odometry_topic:=${ODOMETRY_TOPIC:-/fmu/out/vehicle_odometry}" \
  "foxglove_port:=${FOXGLOVE_PORT:-8765}" &
ros_pid=$!

wait -n "${agent_pid}" "${ros_pid}"
status=$?
exit "${status}"
