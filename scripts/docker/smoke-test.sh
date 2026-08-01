#!/usr/bin/env bash
set -Eeo pipefail

source /usr/local/bin/drn-ros-environment
set -u

foxglove_listening() {
  local port_hex
  port_hex="$(printf '%04X' "${FOXGLOVE_PORT:-8765}")"
  awk -v port=":${port_hex}" '$2 ~ port && $4 == "0A" { found = 1 } END { exit !found }' \
    /proc/net/tcp /proc/net/tcp6
}

quick_smoke() {
  local nodes
  local services
  local topics

  nodes="$(ros2 node list)"
  topics="$(ros2 topic list)"
  services="$(ros2 service list)"

  grep -Fx /foxglove_bridge <<<"${nodes}" >/dev/null
  grep -Fx /odometry_tf_bridge <<<"${nodes}" >/dev/null
  grep -Fx /drn_control <<<"${nodes}" >/dev/null
  grep -Fx /fmu/out/vehicle_odometry <<<"${topics}" >/dev/null
  grep -Fx /drn/control/status <<<"${topics}" >/dev/null
  grep -Fx /drn/control/teleop/xy <<<"${topics}" >/dev/null
  grep -Fx /drn/control/teleop/z_yaw <<<"${topics}" >/dev/null
  grep -Fx /drn/control/activate <<<"${services}" >/dev/null
  grep -Fx /drn/control/takeoff <<<"${services}" >/dev/null
  grep -Fx /drn/control/hold <<<"${services}" >/dev/null
  grep -Fx /drn/control/land <<<"${services}" >/dev/null
  grep -Fx /drn/control/rtl <<<"${services}" >/dev/null
  foxglove_listening
}

full_smoke() {
  local control_status

  # shellcheck disable=SC2016  # Expand inside the child bash process.
  timeout 180 bash -c \
    'until output="$(ros2 topic list)" && grep -Fx /fmu/out/vehicle_odometry <<<"${output}" >/dev/null; do sleep 2; done'
  # shellcheck disable=SC2016  # Expand inside the child bash process.
  timeout 60 bash -c \
    'until output="$(ros2 node list)" && grep -Fx /drn_control <<<"${output}" >/dev/null; do sleep 2; done'
  # shellcheck disable=SC2016  # Expand inside the child bash process.
  timeout 30 bash -c \
    'until output="$(ros2 service list)" && grep -Fx /drn/control/takeoff <<<"${output}" >/dev/null; do sleep 2; done'
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
