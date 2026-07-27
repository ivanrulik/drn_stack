#!/usr/bin/env bash
set -Eeo pipefail

source /opt/ros/humble/setup.bash
source /opt/drn_ws/install/setup.bash
set -u

foxglove_listening() {
  local port_hex
  port_hex="$(printf '%04X' "${FOXGLOVE_PORT:-8765}")"
  awk -v port=":${port_hex}" '$2 ~ port && $4 == "0A" { found = 1 } END { exit !found }' \
    /proc/net/tcp /proc/net/tcp6
}

quick_smoke() {
  ros2 node list | grep -qx /foxglove_bridge
  ros2 node list | grep -qx /odometry_tf_bridge
  ros2 topic list | grep -qx /fmu/out/vehicle_odometry
  foxglove_listening
}

full_smoke() {
  timeout 180 bash -c \
    'until ros2 topic list | grep -qx /fmu/out/vehicle_odometry; do sleep 2; done'
  timeout 60 ros2 topic echo \
    --qos-reliability best_effort \
    --qos-durability volatile \
    --once /fmu/out/vehicle_odometry >/dev/null
  timeout 30 ros2 topic echo \
    --qos-reliability reliable \
    --qos-durability transient_local \
    --once /robot_description >/dev/null
  (
    set +o pipefail
    timeout 15 ros2 run tf2_ros tf2_echo map base_link 2>&1 |
      grep -m1 -q "Translation"
  )
  foxglove_listening
}

case "${1:-full}" in
  full) full_smoke ;;
  quick) quick_smoke ;;
  *)
    echo "Usage: $0 [full|quick]" >&2
    exit 2
    ;;
esac
