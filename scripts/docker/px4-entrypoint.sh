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

exec make px4_sitl "${PX4_SIM_MODEL}"
