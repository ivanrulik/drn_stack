# DRN Stack

Dockerized PX4 v1.17 SITL, Gazebo Harmonic, ROS 2 Humble, and Foxglove visualization for the x500 quadrotor.

![DRN Stack x500 Visualization](resources/drn_viz_x500.png)

The formal architecture, implementation phases, and acceptance criteria are in
[`docs/DOCKER_PLAN.md`](docs/DOCKER_PLAN.md).

## Quick start

### Windows PowerShell

Start Docker Desktop with the Linux container engine, then run:

```powershell
.\scripts\run-sim.ps1
```

### Bash, Git Bash, or WSL

```bash
bash ./scripts/run-sim.sh
```

The first run builds PX4, Gazebo, the Micro XRCE-DDS Agent, and the ROS workspace, so it can take a while. Later runs use Docker's build cache and redeploy only changed images.

When the readiness checks pass:

- Foxglove: `ws://localhost:8765`
- QGroundControl: listens for UDP on `localhost:14550`
- PX4 odometry: `/fmu/out/vehicle_odometry`
- DRN control status: `/drn/control/status`
- Drone transform: `map -> base_link`

Gazebo runs headless. Use Foxglove on the host for 3D visualization.

## Commands

| Action | PowerShell | Bash |
| --- | --- | --- |
| Build/redeploy and start | `.\scripts\run-sim.ps1` | `bash ./scripts/run-sim.sh` |
| Show health and topic status | `.\scripts\status.ps1` | `bash ./scripts/status.sh` |
| Follow all logs | `.\scripts\logs.ps1` | `bash ./scripts/logs.sh` |
| Follow PX4 logs | `.\scripts\logs.ps1 -Service px4-sitl` | `bash ./scripts/logs.sh px4-sitl` |
| Run a command in ROS | `.\scripts\run.ps1 ros2 node list` | `bash ./scripts/run.sh ros2 node list` |
| Restart without rebuilding | `.\scripts\restart.ps1` | `bash ./scripts/restart.sh` |
| Stop and preserve images/cache | `.\scripts\stop.ps1` | `bash ./scripts/stop.sh` |
| Remove this stack's images/state | `.\scripts\clean.ps1 -Force` | `bash ./scripts/clean.sh --yes` |

Normal stop and redeploy operations do not delete Docker images or build caches. Cleanup is deliberately explicit and affects only the `drn-stack` Compose project.

## Docker storage safety

PX4 and ROS image builds can write much more temporary data than their final
images contain. On Docker Desktop with WSL 2, the dynamically allocated
`docker_data.vhdx` can retain that physical space until unused blocks are
trimmed and WSL shuts down.

The run and restart scripts refuse to begin with less than 50 GiB free on the
host filesystem. Set `DRN_MIN_HOST_FREE_GB` only when an intentional override
is needed. Both containers use Docker's bounded, compressed `local` logging
driver so long-running simulations cannot create unbounded JSON logs.

On Windows, reclaim unused VHDX space without pruning Docker data:

```powershell
.\scripts\stop.ps1
.\scripts\reclaim-docker-space.ps1 -Force
```

The reclaim command refuses to proceed while any Docker container is running.
It stops Docker Desktop and all WSL distributions, trims the Docker filesystem,
allows Windows to compact the VHDX, and restarts Docker Desktop. Images,
containers, volumes, and build cache are preserved.

## Quality checks

Run repository linting from Bash, Git Bash, or WSL:

```bash
bash ./scripts/lint.sh
```

The lint command checks shell scripts, YAML, Compose rendering, Python, XML,
and PowerShell syntax when `pwsh` is available. It requires `shellcheck` and
`yamllint`.

Build the pinned ROS workspace and run its ament tests in Docker:

```bash
bash ./scripts/test-ros-build.sh
```

GitHub Actions runs both commands on every push and pull request. The existing
Docker smoke workflow continues to build and exercise the complete simulation.

## Architecture

The stack uses two services:

1. `ros-viz` runs ROS 2, Micro XRCE-DDS Agent, `drn_control`, `drn_viz`, robot state publisher, and Foxglove Bridge.
2. `px4-sitl` runs PX4 and Gazebo Harmonic in headless mode.

The PX4 service shares the ROS service's network namespace. This preserves PX4 SITL's standard XRCE connection to `localhost:8888` without depending on cross-container DDS discovery.

Pinned upstream revisions:

- PX4-Autopilot `v1.17.0`
- `px4_msgs` `v1.17.0`
- `px4_ros_com` commit `86e9aeb20e55a4673fa8a9f1c29ea06a6c5ad1af`
- PX4 ROS 2 Interface Library `release/1.17` commit `4a3370f084ac6f1ef001a4afa2b007845ffd0837`
- Micro XRCE-DDS Agent `v2.4.3`
- ROS 2 Humble on Ubuntu 22.04

## Flight controls

`drn_control` uses the official PX4 ROS 2 Control Interface rather than
reimplementing the raw offboard heartbeat, mode registration, command
acknowledgements, retries, or failsafe ownership. Startup is inert and the
normal smoke test only checks that the interface registered; it never arms or
moves the vehicle.

To fly in SITL:

1. Start the stack and connect QGroundControl.
2. Select the external flight mode named **DRN Control**, or activate it
   through ROS if QGroundControl does not display external modes:

   ```powershell
   .\scripts\run.ps1 ros2 service call /drn/control/activate std_srvs/srv/Trigger '{}'
   ```

   Activation is accepted only while disarmed and does not arm or take off.
3. Request takeoff:

   ```powershell
   .\scripts\run.ps1 ros2 service call /drn/control/takeoff std_srvs/srv/Trigger '{}'
   ```

4. In the imported Foxglove layout, use the 3D panel's pose publishing tool to
   send an absolute target to `/drn/control/setpoint`. Targets use the ROS
   `map` frame in ENU coordinates: x east, y north, and z up. Setpoints are
   ignored unless the vehicle is armed and **DRN Control** is active.
5. Land or return through PX4:

   ```powershell
   .\scripts\run.ps1 ros2 service call /drn/control/land std_srvs/srv/Trigger '{}'
   .\scripts\run.ps1 ros2 service call /drn/control/rtl std_srvs/srv/Trigger '{}'
   ```

The complete topic and service contract, input validation, and recovery
behavior are documented in [`drn_control/README.md`](drn_control/README.md).

## Configuration

The defaults work without creating an environment file. Copy `.env.example` to `.env` only when overrides are needed:

```dotenv
PX4_SIM_MODEL=gz_x500
PX4_GZ_WORLD=default
PX4_SIM_SPEED_FACTOR=1
ROS_DOMAIN_ID=0
FOXGLOVE_PORT=8765
QGC_HOST=host.docker.internal
QGC_PORT=14550
```

The convenience scripts read the same environment variables.
PX4 resolves `QGC_HOST` from inside Docker and sends its GCS MAVLink stream to
`QGC_PORT`; QGroundControl does not need a remote server entry.

## Foxglove

1. Open Foxglove on the host.
2. Add a Foxglove WebSocket connection to `ws://localhost:8765`.
3. Open the **Layouts** menu and select **Import from file...**.
4. Import [`foxglove/drn-simulation.json`](foxglove/drn-simulation.json).

The default layout includes:

- A 3D x500 view using `map` as the fixed frame.
- The `/robot_description` model, map grid, and `map -> base_link` transform.
- Live NED position and velocity plots.
- Vehicle and DRN control status inspectors.
- A pose publishing tool configured for `/drn/control/setpoint`.

The ROS bridge publishes an identity `map -> base_link` transform until the first PX4 odometry message arrives.

## Troubleshooting

### Docker is unavailable

Start Docker Desktop and ensure it is using Linux containers:

```powershell
docker info
docker context show
```

### Startup fails

```powershell
.\scripts\status.ps1
.\scripts\logs.ps1
```

`run-sim` automatically prints the last 100 log lines when a build, health check, ROS topic check, or TF check fails.

### Port conflict

Override the host ports before starting:

```powershell
$env:FOXGLOVE_PORT = "18765"
$env:QGC_PORT = "14551"
.\scripts\run-sim.ps1
```

### Force a clean project rebuild

```powershell
.\scripts\clean.ps1 -Force
.\scripts\run-sim.ps1
```

This does not remove unrelated Docker images or the global Docker build cache.

## Development

`run-sim` always invokes a cached Compose build. Changes under `drn_control/`
or `drn_viz/` invalidate only the relevant ROS image layers, rebuild the
workspace, and recreate the changed service.
