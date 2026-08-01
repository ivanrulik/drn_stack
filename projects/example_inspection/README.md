# Example inspection project

This deliberately small downstream project demonstrates the DRN project
extension contract without modifying `drn_control` or `drn_viz`. Its colcon
overlay installs one ROS 2 node that publishes a text heartbeat. It never
activates a flight mode, arms, takes off, or publishes a motion command.

From the DRN Stack repository root, run:

```powershell
.\scripts\run-scenario.ps1 projects\example_inspection startup-health
```

Or with Bash:

```bash
bash ./scripts/run-scenario.sh projects/example_inspection startup-health
```

The runner builds the pinned base images and the project overlay, starts an
isolated stack, runs the core smoke test and project health assertions, and
then stops the containers while preserving images and build cache.
