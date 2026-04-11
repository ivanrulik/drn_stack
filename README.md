# DRN Stack

Complete PX4 drone visualization and ROS 2 integration stack for SITL simulation.

![DRN Stack x500 Visualization](resources/drn_viz_x500.png)


## Overview

The DRN Stack provides a unified environment for simulating and visualizing PX4 autonomous vehicles in ROS 2 Humble. It bridges PX4 firmware (running in Gazebo SITL) with ROS 2 through the Micro XRCE-DDS protocol and delivers real-time 3D visualization via Foxglove.

## Stack Contents

- **drn_viz**: Core visualization and transform package
  - PX4 ↔ ROS 2 frame transforms (NED ↔ ENU conversion)
  - TF broadcasting from odometry data
  - URDF robot model (x500 quadrotor)
  - Launch orchestration

## Quick Start

### Prerequisites

- ROS 2 Humble
- PX4-Autopilot (cloned to parent workspace)
- Gazebo (for SITL)
- QGroundControl (optional, for GCS control)

### Build

```bash
cd ~/code/ros2_ws
colcon build
source install/setup.bash
```

### Run (independent terminals)

Start the stack in separate terminals so each component can be observed and restarted independently.

**Terminal 1: PX4 SITL + Gazebo**

```bash
cd ~/code/PX4-Autopilot
PX4_SIM_MODEL=gz_x500 PX4_SYS_AUTOSTART=4001 make px4_sitl gz_x500
```

**Terminal 2: Micro XRCE-DDS Agent**

```bash
MicroXRCEAgent udp4 -p 8888
```

If your system provides the lowercase binary name instead:

```bash
micro-xrce-dds-agent udp4 -p 8888
```

**Terminal 3: ROS 2 visualization**

```bash
cd ~/code/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 launch drn_viz visualize.launch.py odometry_topic:=/fmu/out/vehicle_odometry
```

**Terminal 4: QGroundControl (optional)**

Open QGroundControl and connect via UDP on `localhost:14550`.

When all terminals are running:
1. PX4 SITL publishes MAVLink and PX4 ROS topics.
2. XRCE agent bridges PX4 DDS traffic on UDP 8888.
3. `drn_viz` publishes TF/robot model and Foxglove WebSocket.
4. Foxglove is available at `ws://localhost:8765`.

### Connect GCS

Use QGroundControl to connect to:
- **Connection**: UDP
- **Host**: localhost
- **Port**: 14550

## Architecture

```
PX4 SITL (Gazebo)
    ↓
Micro XRCE-DDS Agent (UDP 8888)
    ↓
ROS 2 Topics (/fmu/out/*, /tf)
    ↓
Robot State Publisher (publishes URDF)
Odometry TF Bridge (NED→ENU frame transforms)
Foxglove Bridge (WebSocket 8765)
    ↓
Visualization Clients
    ↓
QGroundControl (MAVLink)
```

## Key Topics

- `/fmu/out/vehicle_odometry` - PX4 odometry (NED frame)
- `/tf` - Transform tree (map → base_link in ENU)
- `/robot_description` - URDF model from x500.urdf

## Dependencies

- `px4_msgs` - PX4 ROS message types
- `px4_ros_com` - Frame transform library
- `geometry_msgs` - ROS geometry types
- `tf2_ros` - ROS 2 transform library
- `robot_state_publisher` - URDF publisher
- `foxglove_bridge` - Visualization bridge

## File Structure

```
drn_stack/
├── README.md              (this file)
└── drn_viz/
    ├── CMakeLists.txt     (build config)
    ├── package.xml        (ROS metadata)
    ├── launch/
    │   └── visualize.launch.py
    ├── src/
    │   └── odometry_tf_bridge.cpp
    ├── urdf/
    │   └── x500.urdf
    └── meshes/
        └── (DAE/STL model files)
```

## Troubleshooting

**Meshes not loading in Foxglove**
- Verify URDF uses `package://drn_viz/meshes/` URIs
- Check meshes deployed to `install/drn_viz/share/drn_viz/meshes/`

**ROS 2 nodes not starting**
- Source setup: `source install/setup.bash`
- Check PX4 SITL terminal is running and not reporting startup errors.

**QGroundControl not connecting**
- Verify PX4 SITL is still running in Terminal 1.
- Check MAVLink listener: `ss -lunp | grep 14550`
- Confirm QGroundControl is using UDP `localhost:14550`.

## Extending the Stack

Add new packages to `src/drn_stack/`:
```bash
ros2 pkg create <new_package> --build-type ament_cmake
```

Update build with:
```bash
colcon build
source install/setup.bash
```

## Control

Currently **monitoring-only**. To add offboard control:
1. Create new package with offboard commander node
2. Subscribe to `/fmu/out/vehicle_odometry`
3. Publish to `/fmu/in/offboard_control_mode` and `/fmu/in/trajectory_setpoint`
4. Add to visualize.launch.py

---

**Status**: Production-ready for SITL visualization and monitoring.  
**Last Updated**: April 2026
