#!/usr/bin/env bash
set -Eeuo pipefail

px4_bin="/opt/PX4-Autopilot/build/px4_sitl_default/bin"

[[ "$(pgrep -cx px4)" -eq 2 ]]
pgrep -f 'gz sim' >/dev/null

"${px4_bin}/px4-param" --instance 1 show MAV_SYS_ID 2>/dev/null |
  grep -Eq 'MAV_SYS_ID .*: 2$'
"${px4_bin}/px4-param" --instance 2 show MAV_SYS_ID 2>/dev/null |
  grep -Eq 'MAV_SYS_ID .*: 3$'
"${px4_bin}/px4-uxrce_dds_client" --instance 1 status 2>/dev/null |
  grep -Fq 'Running, connected'
"${px4_bin}/px4-uxrce_dds_client" --instance 2 status 2>/dev/null |
  grep -Fq 'Running, connected'
