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
  ros2 node list | grep -qx /drn_control
  ros2 topic list | grep -qx /fmu/out/vehicle_odometry
  ros2 topic list | grep -qx /drn/control/status
  ros2 service list | grep -qx /drn/control/takeoff
  ros2 service list | grep -qx /drn/control/hold
  ros2 service list | grep -qx /drn/control/land
  ros2 service list | grep -qx /drn/control/rtl
  foxglove_listening
}

full_smoke() {
  local control_status

  timeout 180 bash -c \
    'until ros2 topic list | grep -qx /fmu/out/vehicle_odometry; do sleep 2; done'
  timeout 60 bash -c \
    'until ros2 node list | grep -qx /drn_control; do sleep 2; done'
  timeout 30 bash -c \
    'until ros2 service list | grep -qx /drn/control/takeoff; do sleep 2; done'
  timeout 60 ros2 topic echo \
    --qos-reliability best_effort \
    --qos-durability volatile \
    --once /fmu/out/vehicle_odometry >/dev/null
  timeout 30 ros2 topic echo \
    --qos-reliability reliable \
    --qos-durability transient_local \
    --once /robot_description >/dev/null
  control_status="$(timeout 30 ros2 topic echo \
    --qos-reliability reliable \
    --qos-durability transient_local \
    --once /drn/control/status)"
  grep -Eq '^data: (inactive|ready_armed|ready_disarmed)$' <<<"${control_status}"
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
