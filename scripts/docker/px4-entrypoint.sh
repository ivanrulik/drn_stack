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

exec make px4_sitl "${PX4_SIM_MODEL}"
