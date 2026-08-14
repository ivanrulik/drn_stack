#!/usr/bin/env bash
set -Eeo pipefail

source /usr/local/bin/drn-ros-environment
set -u

has_capability() {
  local capability="$1"
  [[ ",${DRN_PROFILE_CAPABILITIES:-}," == *",${capability},"* ]]
}

pgrep -x MicroXRCEAgent >/dev/null
nodes="$(ros2 node list 2>/dev/null)"
grep -qx "/foxglove_bridge" <<<"${nodes}"
if has_capability multi-vehicle; then
  grep -qx "/px4_1/odometry_tf_bridge" <<<"${nodes}"
  grep -qx "/px4_2/odometry_tf_bridge" <<<"${nodes}"
  grep -qx "/px4_1/robot_state_publisher" <<<"${nodes}"
  grep -qx "/px4_2/robot_state_publisher" <<<"${nodes}"
  if grep -qx "/drn_control" <<<"${nodes}"; then
    exit 1
  fi
else
  grep -qx "/odometry_tf_bridge" <<<"${nodes}"
fi
if [[ "${DRN_CONNECTION_MODE:-sitl}" == "hardware-udp" ]]; then
  if grep -qx "/drn_control" <<<"${nodes}"; then
    exit 1
  fi
fi
if has_capability depth-camera; then
  ros2 node list 2>/dev/null | grep -qx "/depth_camera_bridge"
fi
if has_capability vision-odometry; then
  ros2 node list 2>/dev/null | grep -qx "/vision_odometry_bridge"
  ros2 node list 2>/dev/null | grep -qx "/vision_odometry_adapter"
fi
if has_capability laser-scan; then
  ros2 node list 2>/dev/null | grep -qx "/lidar_bridge"
  ros2 node list 2>/dev/null | grep -qx "/laser_scan_adapter"
  ros2 node list 2>/dev/null | grep -qx "/lidar_world_markers"
fi
port_hex="$(printf '%04X' "${FOXGLOVE_PORT:-8765}")"
awk -v port=":${port_hex}" '$2 ~ port && $4 == "0A" { found = 1 } END { exit !found }' \
  /proc/net/tcp /proc/net/tcp6
