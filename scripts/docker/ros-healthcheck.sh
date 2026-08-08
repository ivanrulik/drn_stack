#!/usr/bin/env bash
set -Eeo pipefail

source /usr/local/bin/drn-ros-environment
set -u

pgrep -x MicroXRCEAgent >/dev/null
ros2 node list 2>/dev/null | grep -qx "/foxglove_bridge"
ros2 node list 2>/dev/null | grep -qx "/odometry_tf_bridge"
if [[ "${DRN_PROFILE:-x500-basic}" == "x500-depth" ]]; then
  ros2 node list 2>/dev/null | grep -qx "/x500_depth_bridge"
fi
port_hex="$(printf '%04X' "${FOXGLOVE_PORT:-8765}")"
awk -v port=":${port_hex}" '$2 ~ port && $4 == "0A" { found = 1 } END { exit !found }' \
  /proc/net/tcp /proc/net/tcp6
