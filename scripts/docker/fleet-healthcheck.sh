#!/usr/bin/env bash
set -Eeuo pipefail

px4_bin="/opt/PX4-Autopilot/build/px4_sitl_default/bin"
fleet_size="${DRN_FLEET_SIZE:-2}"

[[ "${fleet_size}" =~ ^[0-9]+$ ]]
(( fleet_size >= 2 && fleet_size <= 4 ))
[[ "$(pgrep -cx px4)" -eq "${fleet_size}" ]]
pgrep -f 'gz sim' >/dev/null

for (( instance = 1; instance <= fleet_size; instance++ )); do
  expected_system_id=$((instance + 1))
  "${px4_bin}/px4-param" --instance "${instance}" show MAV_SYS_ID 2>/dev/null |
    grep -Eq "MAV_SYS_ID .*: ${expected_system_id}$"
  "${px4_bin}/px4-uxrce_dds_client" --instance "${instance}" status 2>/dev/null |
    grep -Fq 'Running, connected'
done
