# DRN Control

`drn_control` is a thin operator-facing adapter around the official
`px4_ros2_cpp` control interface for PX4 v1.17. It registers one external mode
named `DRN Control`; it does not publish a hand-written offboard heartbeat or
duplicate PX4 command acknowledgement and retry logic.

The node is inert at startup. An operator must either select `DRN Control` in
QGroundControl or call `/drn/control/activate` while disarmed before any flight
request is accepted. Takeoff uses PX4 preflight checks before arming.

## Interface

| Name | Type | Purpose |
| --- | --- | --- |
| `/drn/control/status` | `std_msgs/msg/String` | Latched lifecycle and error status |
| `/drn/control/setpoint` | `geometry_msgs/msg/PoseStamped` | Absolute `map`-frame ENU position and optional yaw |
| `/drn/control/activate` | `std_srvs/srv/Trigger` | Select DRN Control while disarmed |
| `/drn/control/takeoff` | `std_srvs/srv/Trigger` | Arm with preflight checks, take off, then hold |
| `/drn/control/hold` | `std_srvs/srv/Trigger` | Hold the current local position |
| `/drn/control/land` | `std_srvs/srv/Trigger` | Enter PX4 Land and wait for disarm |
| `/drn/control/rtl` | `std_srvs/srv/Trigger` | Enter PX4 Return and wait for disarm |

Setpoints are accepted only while the external mode is active and armed. The
adapter converts ROS ENU positions and yaw to PX4 NED using the interface
library's frame conversion helpers. A zero quaternion leaves heading
unconstrained. Commands with the wrong frame, non-finite values, excessive
position magnitude, or meaningful roll/pitch are rejected.

The launch file respawns the control process if PX4 is not available yet or the
interface watchdog stops the process after an FMU disconnect. This preserves
the upstream watchdog rather than bypassing its safety behavior.

## Current scope and upstream constraints

- The PX4 ROS 2 Control Interface is still documented as experimental. This
  package pins its `release/1.17` branch to the exact commit built with PX4
  v1.17 and `px4_msgs` v1.17.
- Only one external mode is registered. This stays below the PX4 v1.17
  `ArmingCheckReply` queue-overflow case reported when more than four custom
  modes are registered.
- This stack is single-vehicle. Multi-vehicle mode/executor naming and
  isolation have an open upstream issue and are intentionally out of scope.
- The executor treats cancellation as terminal and uses generation guards so a
  cancelled callback cannot schedule a new mode from inside the interface
  library's cancellation path.
- Automated smoke tests verify registration, status, services, odometry, TF,
  and Foxglove without arming. Takeoff, setpoint tracking, Land, RTL, and PX4
  restart recovery still require an explicit operator-in-the-loop SITL test.

Relevant upstream tracking:

- [PX4 ROS 2 Control Interface documentation](https://docs.px4.io/v1.17/en/ros2/px4_ros2_control_interface)
- [Health check timeout behavior](https://github.com/Auterion/px4-ros2-interface-lib/issues/195)
- [Mode scheduling cancellation assertion](https://github.com/Auterion/px4-ros2-interface-lib/issues/167)
- [Multi-vehicle executor behavior](https://github.com/Auterion/px4-ros2-interface-lib/issues/191)
