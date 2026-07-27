# Docker Development and Operations Plan

## Objective

Provide a reproducible local environment that builds and runs the DRN PX4
simulation without requiring ROS 2, PX4, Gazebo, or the XRCE-DDS Agent on the
host. Docker Desktop with the Linux container engine is the only runtime
prerequisite.

## Delivered architecture

| Service | Responsibility | Health signal |
| --- | --- | --- |
| `ros-viz` | ROS 2 Humble, Micro XRCE-DDS Agent, `drn_viz`, robot state publisher, and Foxglove Bridge | ROS nodes are present and Foxglove is listening |
| `px4-sitl` | PX4 v1.17 SITL and headless Gazebo Harmonic | PX4 process is running and the XRCE agent is reachable |

PX4 shares the `ros-viz` network namespace so its standard
`localhost:8888` XRCE endpoint works without relying on cross-container DDS
discovery. The host exposes Foxglove on TCP 8765 and QGroundControl MAVLink on
UDP 14550.

## Implementation phases

- [x] Define pinned, multi-stage Docker builds for PX4 and ROS.
- [x] Define the two-service Compose topology, health checks, ports, and
  restart behavior.
- [x] Add idempotent Bash and PowerShell controllers for build/redeploy,
  restart, status, logs, stop, and explicit cleanup.
- [x] Configure Foxglove for container access and declare all ROS package
  dependencies.
- [x] Add local and CI smoke tests.
- [x] Document normal operation, configuration, and troubleshooting.

## Operational contract

- `scripts/run-sim` performs cached builds, recreates the stack, waits for both
  services to become healthy, and runs the full smoke test.
- `scripts/restart` restarts existing images without rebuilding and repeats the full
  smoke test.
- `scripts/status` reports Compose health and runs a quick ROS/Foxglove check.
- `scripts/stop` removes containers and the Compose network while preserving images
  and build cache.
- `scripts/clean` requires explicit confirmation and removes only resources owned by
  the `drn-stack` Compose project.

## Acceptance criteria

A deployment is ready only when all of the following pass:

1. Both Compose services report healthy.
2. `/foxglove_bridge` and `/odometry_tf_bridge` are present.
3. PX4 advertises and publishes `/fmu/out/vehicle_odometry`.
4. `/robot_description` can be read with transient-local QoS.
5. A `map -> base_link` transform can be resolved.
6. Foxglove is listening on the configured port.

## Development workflow

1. Modify application or container sources.
2. Run `scripts/run-sim` to rebuild only invalidated Docker layers and redeploy.
3. Use `scripts/status` for a concise health check and `scripts/logs` for live diagnosis.
4. Run `scripts/stop` when finished. Use `scripts/clean` only when a clean image rebuild is
   intentionally required.

The CI workflow renders the Compose configuration, builds both images, starts
the stack, and applies the same smoke-test contract used locally.
