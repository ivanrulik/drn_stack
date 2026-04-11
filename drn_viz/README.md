# drn_viz

ROS 2 visualization package for the PX4 x500 model in Foxglove.

This package publishes an x500 robot description from a local URDF and starts Foxglove Bridge so the model can be rendered in a 3D panel.

It also launches a C++ bridge node from `drn_viz` that publishes a live `map -> base_link` transform from PX4 odometry so the model moves in the 3D view.
Before the first odometry packet arrives, an identity `map -> base_link` transform is published so `map` is always present.

## What this package contains

- `urdf/x500.urdf`: Minimal x500 visual model (base + rotors).
- `meshes/`: Mesh assets copied from PX4 x500_base model.
- `launch/visualize.launch.py`: Launches `robot_state_publisher` and `foxglove_bridge`.
- `drn_viz/odometry_tf_bridge` (C++): Converts PX4 `VehicleOdometry` to TF (`map -> base_link`) using `px4_ros_com` frame transforms.

## Prerequisites

- ROS 2 Humble (or compatible distro).
- `foxglove_bridge` installed in your ROS environment.
- `px4_ros_com` available in the workspace (used by the C++ TF bridge).
- PX4 source tree available at `/home/ivanrulik/code/PX4-Autopilot` if you use the full stack script.

Optional:

- `joint_state_publisher` (launch supports it if present).

## Build

From the workspace root:

```bash
cd /home/ivanrulik/code/ros2_ws
colcon build --packages-select px4_msgs px4_ros_com drn_viz
source install/setup.bash
```

## Run visualization only

```bash
cd /home/ivanrulik/code/ros2_ws
source install/setup.bash
ros2 launch drn_viz visualize.launch.py
```

### Launch arguments

- `urdf`: Absolute path to URDF file.
- `use_joint_state_publisher`: `true` or `false` (default: `false`).
- `odometry_topic`: PX4 odometry topic (default: `/fmu/out/vehicle_odometry`).
- `world_frame`: parent TF frame for motion (default: `map`).
- `base_frame`: drone frame name (default: `base_link`).

Example:

```bash
ros2 launch drn_viz visualize.launch.py use_joint_state_publisher:=true
```

If your PX4 bridge publishes odometry on a different topic:

```bash
ros2 launch drn_viz visualize.launch.py odometry_topic:=/vehicle_odometry
```

If `joint_state_publisher` is not installed, launch will continue and print a skip message.

## Run full PX4 + DDS + visualization stack

Use the workspace helper script:

```bash
cd /home/ivanrulik/code/ros2_ws
./run_viz.sh start
```

The script does the following:

1. Starts PX4 SITL headless (`make px4_sitl gz_x500`).
2. Starts Micro XRCE-DDS Agent on UDP 8888.
3. Sources ROS environment and launches `drn_viz`.
4. Cleans up started background processes on exit.

### Stop or inspect the stack

```bash
cd /home/ivanrulik/code/ros2_ws
./run_viz.sh status
./run_viz.sh stop
```

- `status` prints matching process list and port 8765 listener state.
- `status` also checks odometry topic presence and whether messages are arriving.
- `stop` sends termination to the launch, XRCE agent, and PX4 SITL processes. All processes are cleaned up gracefully.

To use a different odometry topic with the helper script:

```bash
cd /home/ivanrulik/code/ros2_ws
ODOMETRY_TOPIC=/vehicle_odometry ./run_viz.sh start
```

## Foxglove settings

- Connection: `ws://px4-box.orb.local:8765`
- Add a 3D panel and add `Robot Model` layer.
- Set Robot Model source to topic: `/robot_description`
- Set TF follow frame: `base_link`
- Set 3D panel fixed/reference frame to `map`

## Notes

- The x500 URDF is intentionally minimal for stable visualization and does not replicate Gazebo motor plugins or sensors.
- A common `robot_state_publisher` warning may appear about root-link inertia; this is expected and does not block visualization.
- The `odometry_tf_bridge` node is **read-only** and only subscribes to PX4 odometry. It does not send any commands or modify PX4 state.
- The TF bridge now uses the upstream `px4_ros_com` frame transform library for NED/ENU and orientation conversion.

## Troubleshooting

### Foxglove connection issues

If Foxglove shows:

"Check that the WebSocket server at ws://px4-box.orb.local:8765 is reachable."

Check these in order:

1. Verify listener:

```bash
ss -ltnp | grep 8765
```

2. Verify stack state:

```bash
cd /home/ivanrulik/code/ros2_ws
./run_viz.sh status
```

3. Try local connection first:

- `ws://localhost:8765`

4. If using `px4-box.orb.local`, verify name resolution/routing on your client machine. In some setups this hostname resolves to IPv6 only.

### PX4 preflight warnings in startup

You may see warnings like:

```
WARN  [health_and_arming_checks] Preflight Fail: Attitude failure (roll)
WARN  [health_and_arming_checks] Preflight Fail: heading estimate invalid
WARN  [health_and_arming_checks] Preflight Fail: ekf2 missing data
```

These are **harmless preflight checks** in SITL simulation and do **not** prevent flight:

- They appear early in the startup sequence as sensors initialize
- They are not related to the ROS visualization package (which is read-only)
- The drone can arm and fly despite these warnings in SITL

If you want to clear them, wait a few seconds for the EKF to converge or you can arm the drone anyway.
