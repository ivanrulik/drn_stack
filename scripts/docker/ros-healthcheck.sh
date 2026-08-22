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
  fleet_size="${DRN_FLEET_SIZE:-2}"
  [[ "${fleet_size}" =~ ^[0-9]+$ ]]
  (( fleet_size >= 2 && fleet_size <= 4 ))
  for (( instance = 1; instance <= fleet_size; instance++ )); do
    grep -qx "/px4_${instance}/odometry_tf_bridge" <<<"${nodes}"
    grep -qx "/px4_${instance}/robot_state_publisher" <<<"${nodes}"
  done
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
if has_capability precision-landing; then
  ros2 node list 2>/dev/null | grep -qx "/landing_camera_bridge"
  ros2 node list 2>/dev/null | grep -qx "/landing_target_detector"
fi
port_hex="$(printf '%04X' "${FOXGLOVE_PORT:-8765}")"
awk -v port=":${port_hex}" '$2 ~ port && $4 == "0A" { found = 1 } END { exit !found }' \
  /proc/net/tcp /proc/net/tcp6
