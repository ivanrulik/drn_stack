#!/usr/bin/env bash
set -Eeuo pipefail

cd /opt/PX4-Autopilot

export HEADLESS=1
export PX4_SIM_MODEL="${PX4_SIM_MODEL:-gz_x500}"
export PX4_GZ_WORLD="${PX4_GZ_WORLD:-default}"
export PX4_SIM_SPEED_FACTOR="${PX4_SIM_SPEED_FACTOR:-1}"
export PX4_NET_INTERFACE="${PX4_NET_INTERFACE:-eth0}"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
export PX4_UXRCE_DDS_PORT="${XRCE_PORT:-8888}"
export MAKEFLAGS="${MAKEFLAGS:--j4}"
export QGC_PORT="${QGC_PORT:-14550}"

QGC_HOST="${QGC_HOST:-host.docker.internal}"
QGC_HOST_IP="$(
  getent ahostsv4 "${QGC_HOST}" |
    awk 'NR == 1 { print $1 }' ||
    true
)"

if [[ -z "${QGC_HOST_IP}" && "${QGC_HOST}" == "host.docker.internal" ]]; then
  gateway_hex="$(
    awk '$2 == "00000000" { print $3; exit }' /proc/net/route
  )"
  if [[ "${gateway_hex}" =~ ^[[:xdigit:]]{8}$ ]]; then
    QGC_HOST_IP="$(
      printf '%d.%d.%d.%d' \
        "$((16#${gateway_hex:6:2}))" \
        "$((16#${gateway_hex:4:2}))" \
        "$((16#${gateway_hex:2:2}))" \
        "$((16#${gateway_hex:0:2}))"
    )"
  fi
fi

if [[ -z "${QGC_HOST_IP}" ]]; then
  echo "Unable to resolve QGroundControl host '${QGC_HOST}'." >&2
  exit 1
fi

if [[ ! "${QGC_PORT}" =~ ^[0-9]+$ ]] ||
  (( QGC_PORT < 1 || QGC_PORT > 65535 )); then
  echo "Invalid QGroundControl UDP port '${QGC_PORT}'." >&2
  exit 1
fi

export QGC_HOST_IP

if [[ "${DRN_GPU_ACCELERATION:-software}" == "nvidia" ]]; then
  /usr/local/bin/drn-gpu-renderer-check
fi

fleet_size="${DRN_FLEET_SIZE:-1}"
if [[ ! "${fleet_size}" =~ ^[0-9]+$ ]] ||
  (( fleet_size != 1 && (fleet_size < 2 || fleet_size > 4) )); then
  echo "DRN_FLEET_SIZE must be 1 or an integer from 2 through 4." >&2
  exit 2
fi

if (( fleet_size >= 2 )); then
  px4_binary="/opt/PX4-Autopilot/build/px4_sitl_default/bin/px4"
  fleet_pids=()

  # shellcheck disable=SC2317 # Invoked indirectly by trap.
  shutdown_fleet() {
    trap - TERM INT EXIT
    for pid in "${fleet_pids[@]}"; do
      if kill -0 "${pid}" 2>/dev/null; then
        kill -TERM "${pid}" 2>/dev/null || true
      fi
    done
    pkill -TERM -f 'gz sim' 2>/dev/null || true
    for pid in "${fleet_pids[@]}"; do
      wait "${pid}" 2>/dev/null || true
    done
  }
  trap shutdown_fleet TERM INT EXIT

  wait_for_vehicle_odometry() {
    local instance="$1"
    local pid="$2"
    local deadline=$((SECONDS + 60))
    local output

    while (( SECONDS < deadline )); do
      if ! kill -0 "${pid}" 2>/dev/null; then
        echo "PX4 instance ${instance} exited before publishing odometry." >&2
        return 1
      fi
      output="$(
        "${px4_binary%/px4}/px4-listener" \
          --instance "${instance}" vehicle_odometry -n 1 2>/dev/null || true
      )"
      if grep -Fq 'timestamp:' <<<"${output}"; then
        return 0
      fi
      sleep 1
    done

    echo "PX4 instance ${instance} did not publish odometry within 60 seconds." >&2
    return 1
  }

  for (( instance = 1; instance <= fleet_size; instance++ )); do
    spawn_index=$((instance - 1))
    spawn_x=$(((spawn_index / 2) * 2))
    spawn_y=$(((spawn_index % 2) * 2))
    instance_environment=(
      "PX4_SYS_AUTOSTART=4001"
      "PX4_UXRCE_DDS_NS=px4_${instance}"
      "PX4_GZ_MODEL_POSE=${spawn_x},${spawn_y}"
      "GZ_IP=127.0.0.1"
    )
    if (( instance > 1 )); then
      instance_environment+=("PX4_GZ_STANDALONE=1")
    fi

    env "${instance_environment[@]}" "${px4_binary}" -i "${instance}" &
    instance_pid="$!"
    fleet_pids+=("${instance_pid}")
    wait_for_vehicle_odometry "${instance}" "${instance_pid}"
  done

  set +e
  wait -n "${fleet_pids[@]}"
  status=$?
  set -e
  exit "${status}"
fi

exec make px4_sitl "${PX4_SIM_MODEL}"
