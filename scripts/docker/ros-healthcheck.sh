#!/usr/bin/env bash
set -Eeo pipefail

source /opt/ros/humble/setup.bash
source /opt/drn_ws/install/setup.bash
set -u

pgrep -x MicroXRCEAgent >/dev/null
ros2 node list 2>/dev/null | grep -qx "/foxglove_bridge"
ros2 node list 2>/dev/null | grep -qx "/odometry_tf_bridge"
port_hex="$(printf '%04X' "${FOXGLOVE_PORT:-8765}")"
awk -v port=":${port_hex}" '$2 ~ port && $4 == "0A" { found = 1 } END { exit !found }' \
  /proc/net/tcp /proc/net/tcp6
