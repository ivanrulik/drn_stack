# DRN Control

`drn_control` is a thin operator-facing adapter around the official
`px4_ros2_cpp` control interface for PX4 v1.17. It registers the
operator-selected `DRN Control` mode and a separately scheduled `DRN Precision
Land` mode; it does not publish a hand-written offboard heartbeat or duplicate
PX4 command acknowledgement and retry logic.

The node is inert at startup. An operator must either select `DRN Control` in
QGroundControl or call `/drn/control/activate` while disarmed before any flight
request is accepted. Takeoff uses PX4 preflight checks before arming.

## Interface

| Name | Type | Purpose |
| --- | --- | --- |
| `/drn/control/status` | `std_msgs/msg/String` | Latched lifecycle and error status |
| `/drn/control/setpoint` | `geometry_msgs/msg/PoseStamped` | Absolute `map`-frame ENU position and optional yaw |
| `/drn/control/teleop/xy` | `geometry_msgs/msg/Twist` | Body-relative forward/left mouse commands |
| `/drn/control/teleop/z_yaw` | `geometry_msgs/msg/Twist` | Up/down and counterclockwise yaw mouse commands |
| `/drn/control/activate` | `std_srvs/srv/Trigger` | Select DRN Control while disarmed |
| `/drn/control/takeoff` | `std_srvs/srv/Trigger` | Arm with preflight checks, take off, then hold |
| `/drn/control/hold` | `std_srvs/srv/Trigger` | Hold the current local position |
| `/drn/control/land` | `std_srvs/srv/Trigger` | Enter PX4 Land and wait for disarm |
| `/drn/control/rtl` | `std_srvs/srv/Trigger` | Enter PX4 Return and wait for disarm |
| `/drn/control/precision_land` | `std_srvs/srv/Trigger` | Start target-relative landing from armed Hold |
| `/drn/control/precision_land/abort` | `std_srvs/srv/Trigger` | Cancel precision landing and return to Hold |
| `/drn/sensors/landing/target_pose` | `geometry_msgs/msg/PoseStamped` | Marker position in `landing_camera_optical` |

Setpoints are accepted only while the external mode is active and armed. The
adapter converts ROS ENU positions and yaw to PX4 NED using the interface
library's frame conversion helpers. A zero quaternion leaves heading
unconstrained. Commands with the wrong frame, non-finite values, excessive
position magnitude, or meaningful roll/pitch are rejected.

Teleop commands follow the ROS body FLU convention: positive `linear.x` is
forward, positive `linear.y` is left, positive `linear.z` is up, and positive
`angular.z` turns counterclockwise. The controller rotates horizontal motion
using the current PX4 heading and advances the existing smooth GoTo target.
The two topics expire independently after `teleop_timeout_s` (default 0.3 s).
When all movement stops or expires, the controller captures the current local
position and heading and holds there.

Only the documented fields are accepted on each Teleop topic. Horizontal
vector magnitude, vertical velocity, and yaw rate are clamped to
`max_horizontal_speed_m_s`, `max_vertical_speed_m_s`, and
`max_heading_rate_rad_s`. Integration steps are capped by
`max_teleop_step_s` (default 0.1 s), preventing a delayed update from causing a
large target jump.

A fresh nonzero Teleop command owns movement until it is released or times
out. Absolute `/drn/control/setpoint` messages are rejected during that
interval. The Hold, Land, and RTL service paths clear Teleop input before
continuing. No Teleop input can activate the mode, arm, or take off.

The launch file respawns the control process if PX4 is not available yet or the
interface watchdog stops the process after an FMU disconnect. This preserves
the upstream watchdog rather than bypassing its safety behavior.

## Precision-landing safety behavior

The precision-landing request is accepted only while armed, while `DRN
Control` is actively holding, and while the target and PX4 attitude are fresh.
It converts the downward optical-frame translation to body FRD and then NED,
limits horizontal velocity, requires continuous alignment before descending,
and pauses descent if alignment degrades. At 0.6 metres it hands the final
touchdown and disarm to PX4 Land. A stale or invalid target completes the landing mode as failed
and schedules DRN Control Hold; there is no autonomous search behavior.

Hold, Land, RTL, and the dedicated abort service can preempt precision landing.
The mode never activates DRN Control, arms, or takes off. Its target detector
and profile may start automatically because they are observation-only; an
operator remains responsible for every armed SITL step.

## Current scope and upstream constraints

- The PX4 ROS 2 Control Interface is still documented as experimental. This
  package pins its `release/1.17` branch to the exact commit built with PX4
  v1.17 and `px4_msgs` v1.17.
- Only two external modes are registered. This stays below the PX4 v1.17
  `ArmingCheckReply` queue-overflow case reported when more than four custom
  modes are registered.
- `drn_control` remains single-vehicle and is not launched by the observation-
  only `x500-multi` profile. Multi-vehicle mode/executor naming and isolation
  have an open upstream issue and remain intentionally out of scope.
- The executor treats cancellation as terminal and uses generation guards so a
  cancelled callback cannot schedule a new mode from inside the interface
  library's cancellation path.
- Automated smoke tests verify registration, status, services, odometry, TF,
  Teleop subscriptions, and Foxglove without arming. Takeoff, mouse movement,
  setpoint tracking, command-loss Hold, precision landing and abort, Land, RTL,
  and PX4 restart recovery still require an explicit operator-in-the-loop SITL
  test.

Relevant upstream tracking:

- [PX4 ROS 2 Control Interface documentation](https://docs.px4.io/v1.17/en/ros2/px4_ros2_control_interface)
- [Health check timeout behavior](https://github.com/Auterion/px4-ros2-interface-lib/issues/195)
- [Mode scheduling cancellation assertion](https://github.com/Auterion/px4-ros2-interface-lib/issues/167)
- [Multi-vehicle executor behavior](https://github.com/Auterion/px4-ros2-interface-lib/issues/191)
