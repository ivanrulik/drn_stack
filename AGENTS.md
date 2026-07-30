# AGENTS.md

## Project overview

DRN Stack is a Dockerized drone-development environment containing:

- PX4 v1.17 SITL and headless Gazebo Harmonic
- ROS 2 Humble and the PX4 ROS 2 Interface Library
- Micro XRCE-DDS Agent
- Foxglove Bridge and a project-specific Foxglove layout
- `drn_control`, the supported high-level flight-control node
- `drn_viz`, the odometry, TF, robot-model, and visualization package

The primary development host is Windows with PowerShell. Bash scripts must
also continue to work in Linux, Git Bash, and WSL.

## Repository map

- `compose.yaml`: two-service simulation topology
- `docker/`: pinned PX4 and ROS images
- `drn_control/`: flight-mode services, pose targets, and mouse Teleop adapter
- `drn_viz/`: ROS launch files, TF bridge, and x500 model
- `foxglove/drn-simulation.json`: importable default Foxglove layout
- `scripts/`: matching PowerShell and Bash lifecycle and validation commands
- `docs/DOCKER_PLAN.md`: architecture, implementation phases, and acceptance criteria

## Architecture invariants

- Keep the upstream versions and commit pins reproducible. Do not update them
  incidentally.
- PX4 shares the `ros-viz` network namespace so XRCE can use
  `localhost:8888`. Preserve this topology unless the architecture is being
  deliberately redesigned.
- Use the official PX4 ROS 2 Control Interface. Do not replace its mode
  registration, watchdog, acknowledgement, or failsafe behavior with ad hoc
  raw command publishing.
- Startup and automated smoke tests must remain inert: never arm, take off, or
  move the vehicle automatically.
- Armed flight validation is an explicit operator-in-the-loop SITL activity.
- Teleop cannot activate the mode, arm, or take off. Command loss must result
  in a bounded stop/hold, and Hold, Land, and RTL must cancel Teleop input.
- ROS-facing motion uses ENU/FLU conventions; convert explicitly at the PX4
  boundary, where local position and heading use NED conventions.
- Foxglove must bind to localhost by default. Keep client publication and
  service access restricted to the documented control allowlists.
- Normal stop/restart operations preserve images and build cache. Destructive
  cleanup must remain explicit and limited to the `drn-stack` Compose project.

## Common commands

Prefer the PowerShell commands on Windows:

```powershell
.\scripts\run-sim.ps1
.\scripts\status.ps1
.\scripts\logs.ps1
.\scripts\run.ps1 ros2 node list
.\scripts\restart.ps1
.\scripts\stop.ps1
```

Linux, Git Bash, and WSL equivalents:

```bash
bash ./scripts/run-sim.sh
bash ./scripts/status.sh
bash ./scripts/logs.sh
bash ./scripts/run.sh ros2 node list
bash ./scripts/restart.sh
bash ./scripts/stop.sh
```

Do not bypass the lifecycle scripts' host-free-space checks during ordinary
operation.

## Required validation

Run checks proportional to the change. Before a PR that affects runtime code,
containers, control behavior, or visualization, run:

```bash
bash ./scripts/lint.sh
bash ./scripts/test-ros-build.sh
```

For a full integration change, also start the stack and verify:

```bash
bash ./scripts/run-sim.sh
bash ./scripts/status.sh
docker compose --project-name drn-stack exec -T ros-viz \
  /usr/local/bin/drn-smoke-test full
```

On a Windows host without a working Bash/WSL environment, run the equivalent
Docker, Compose, and PowerShell commands directly and report that substitution.

Control changes require focused unit tests for frame conversion, validation,
limits, arbitration, and timeout behavior. Do not claim mouse-flight,
takeoff, Land, RTL, or restart recovery was validated unless an operator
actually performed that SITL test.

## Editing conventions

- Preserve the existing C++ and ROS 2 style and keep ament linters passing.
- Keep matching PowerShell and Bash workflows behaviorally equivalent.
- Follow `.gitattributes`: shell, YAML, JSON, and Docker-related files use LF;
  PowerShell files use CRLF.
- Update the saved Foxglove layout and its lint assertions together when
  control panels or topics change.
- Update `README.md` and package documentation when commands, endpoints,
  safety behavior, or operator procedures change.
- Never add secrets, machine-specific paths, build outputs, or generated ROS
  workspaces to Git.

## Git and review

- Work on a `codex/` branch unless the user requests another branch name.
- Preserve unrelated user changes in a dirty worktree.
- Do not stage, commit, push, create a PR, or merge without explicit user
  authorization.
- PR descriptions should list validation performed and clearly identify any
  operator-in-the-loop flight checks that remain pending.
