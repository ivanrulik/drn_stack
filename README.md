# DRN Stack

Complete PX4 drone visualization and ROS 2 integration stack for SITL simulation.

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

### Run

```bash
./run_viz.sh start
```

This starts:
1. PX4 SITL with x500 in Gazebo
2. Micro XRCE-DDS Agent (UDP port 8888)
3. ROS 2 nodes: robot_state_publisher, foxglove_bridge, odometry_tf_bridge
4. Foxglove available at `http://localhost:8765`

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
- Check Gazebo is running: `ps aux | grep gazebo`

**QGroundControl not connecting**
- Verify PX4 SITL started: `ps aux | grep px4`
- Check MAVLink port: `netstat -tln | grep 14550`

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
