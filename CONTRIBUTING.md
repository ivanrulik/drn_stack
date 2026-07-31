# Contributing to DRN Stack

Thank you for helping improve DRN Stack. The project favors small,
reviewable changes that preserve its reproducible and safety-conscious
simulation workflow.

## Before starting

- Search existing issues and pull requests for related work.
- Open an issue before a substantial architecture or safety change.
- Base work on the current `main` branch.
- Use a descriptive branch such as `feature/project-manifest`,
  `fix/teleop-timeout`, or `docs/compatibility-policy`.

Do not include secrets, machine-specific paths, build output, generated ROS
workspaces, or unrelated cleanup.

## Development workflow

The supported development entrypoint is the repository-level Docker workflow.
On Windows, prefer PowerShell:

```powershell
.\scripts\run-sim.ps1
.\scripts\status.ps1
```

On Linux, Git Bash, or WSL:

```bash
bash ./scripts/run-sim.sh
bash ./scripts/status.sh
```

Normal stop and restart commands preserve Docker images and build cache.
Do not bypass the host-free-space checks or use global Docker pruning as part
of ordinary development.

## Safety boundaries

- Startup, health checks, and automated smoke tests must remain disarmed and
  motionless.
- Armed or moving SITL tests require an explicit operator.
- Teleoperation must never activate the DRN mode, arm, or take off.
- Preserve PX4 ownership of mode registration, acknowledgements, watchdogs,
  and failsafes through the official ROS 2 Control Interface.
- Keep ROS-facing motion in ENU/FLU and convert explicitly at the PX4 NED
  boundary.
- Keep Foxglove bound to localhost by default and restrict its control
  allowlists.
- Hardware access must never be selected implicitly.

Describe any operator-in-the-loop validation that was not performed in the
pull request.

## Required checks

Run checks proportional to the change. Before a pull request that changes
runtime code, containers, control behavior, package metadata, or
visualization, run:

```bash
bash ./scripts/lint.sh
bash ./scripts/test-ros-build.sh
```

For full integration changes, also run:

```bash
bash ./scripts/run-sim.sh
bash ./scripts/status.sh
docker compose --project-name drn-stack exec -T ros-viz \
  /usr/local/bin/drn-smoke-test full
```

Control changes also require focused tests for frame conversion, validation,
limits, arbitration, and timeouts. Do not claim that takeoff, movement, Land,
RTL, or restart recovery passed unless an operator performed that SITL test.

## Pull requests

Keep pull requests focused and include:

- the user-visible outcome;
- the reason for the change;
- important safety and compatibility effects;
- exact validation commands and results;
- any operator or hardware checks still pending.

All required GitHub checks must pass before merge.
