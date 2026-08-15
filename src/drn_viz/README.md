# drn_viz

ROS 2 visualization, transform, and profile-sensor adaptation package. The
current bundled robot model is the PX4 x500.

The package:

- Publishes the x500 URDF and mesh resources.
- Converts PX4 NED odometry to ROS ENU coordinates.
- Publishes `map -> base_link`.
- Starts Foxglove Bridge.
- Publishes an identity transform before the first odometry packet.
- Selects profile-specific ROS bridges by declared capability rather than
  airframe name.
- Normalizes simulated vision odometry to `map` -> `base_link` in ENU/FLU.
- Bridges rendered 2D LiDAR through a stable `lidar_link` LaserScan contract.
- Generates isolated TF and robot-model observation paths for two to four
  namespaced x500 instances in the bounded fleet profile.

## Docker workflow

Use the repository-level commands:

```bash
bash ./scripts/run-sim.sh
bash ./scripts/status.sh
bash ./scripts/logs.sh ros-viz
bash ./scripts/stop.sh
```

Foxglove connects to `ws://localhost:8765`.

## Native ROS workspace

The repository itself uses the conventional ROS 2 workspace layout, with
`drn_viz` and `drn_control` under the root `src/` directory. The Docker workflow
is the supported project entrypoint because it also supplies the pinned
`px4_msgs`, `px4_ros_com`, and PX4 ROS 2 Interface Library dependencies.

For package-only development in another ROS 2 Humble workspace, place
`drn_viz`, `drn_control`, and matching upstream dependencies under that
workspace's `src/` directory:

```bash
source /opt/ros/humble/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --packages-up-to drn_viz
source install/setup.bash
ros2 launch drn_viz visualize.launch.py
```

## Launch arguments

- `urdf`: absolute path to the URDF.
- `use_joint_state_publisher`: defaults to `false`.
- `odometry_topic`: defaults to `/fmu/out/vehicle_odometry`.
- `world_frame`: defaults to `map`.
- `base_frame`: defaults to `base_link`.
- `foxglove_port`: defaults to `8765`.
- `profile`: selected profile directory name; defaults to `x500-basic`.
- `airframe`: declared airframe family; defaults to `x500`.
- `capabilities`: comma-separated profile capabilities.
- `model_name`: spawned Gazebo model instance; defaults to `x500_0`.
- `world_name`: Gazebo world used to resolve transport topics.
- `fleet_size` (`fleet.launch.py` only): bounded vehicle count from two through
  four; defaults to `DRN_FLEET_SIZE` or two.

Example:

```bash
ros2 launch drn_viz visualize.launch.py \
  odometry_topic:=/fmu/out/vehicle_odometry \
  foxglove_port:=8765
```

The node is read-only and does not publish PX4 commands.

With the `vision-odometry` capability, `ros_gz_bridge` receives Gazebo's
covariance-bearing model odometry on an internal topic. The
`vision_odometry_adapter` republishes it as
`/drn/sensors/vision/odometry` with stable ROS ENU/FLU frame labels. It does not
configure PX4 estimator fusion or implement a camera/IMU VIO algorithm.

With the `laser-scan` capability, `ros_gz_bridge` receives the selected model's
rendered scan on an internal topic. `laser_scan_adapter` republishes it as
`/drn/sensors/lidar/scan` with the stable `lidar_link` frame, while the launch
file publishes `base_link -> lidar_link`. It does not enable collision
prevention or publish vehicle commands.
