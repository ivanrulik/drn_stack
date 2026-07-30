# drn_viz

ROS 2 visualization and transform package for the PX4 x500 model.

The package:

- Publishes the x500 URDF and mesh resources.
- Converts PX4 NED odometry to ROS ENU coordinates.
- Publishes `map -> base_link`.
- Starts Foxglove Bridge.
- Publishes an identity transform before the first odometry packet.

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

Example:

```bash
ros2 launch drn_viz visualize.launch.py \
  odometry_topic:=/fmu/out/vehicle_odometry \
  foxglove_port:=8765
```

The node is read-only and does not publish PX4 commands.
