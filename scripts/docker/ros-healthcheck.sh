#!/usr/bin/env bash
set -Eeo pipefail

source /usr/local/bin/drn-ros-environment
set -u

has_capability() {
  local capability="$1"
  [[ ",${DRN_PROFILE_CAPABILITIES:-}," == *",${capability},"* ]]
}

pgrep -x MicroXRCEAgent >/dev/null
ros2 node list 2>/dev/null | grep -qx "/foxglove_bridge"
ros2 node list 2>/dev/null | grep -qx "/odometry_tf_bridge"
if has_capability depth-camera; then
  ros2 node list 2>/dev/null | grep -qx "/depth_camera_bridge"
fi
if has_capability vision-odometry; then
  ros2 node list 2>/dev/null | grep -qx "/vision_odometry_bridge"
  ros2 node list 2>/dev/null | grep -qx "/vision_odometry_adapter"
fi
port_hex="$(printf '%04X' "${FOXGLOVE_PORT:-8765}")"
awk -v port=":${port_hex}" '$2 ~ port && $4 == "0A" { found = 1 } END { exit !found }' \
  /proc/net/tcp /proc/net/tcp6
