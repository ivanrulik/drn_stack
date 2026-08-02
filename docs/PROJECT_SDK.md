# Project and scenario extension contract

DRN Stack projects add downstream ROS 2 packages and versioned validation
scenarios without copying or modifying the core workspace. Schema version 1
remains strictly inert. Schema version 2 adds one disarmed, operator-gated PX4
SITL battery-failure action; it cannot arm, move, land, or target hardware.

## Run the example

From the DRN Stack repository root:

```powershell
.\scripts\run-scenario.ps1 projects\example_inspection startup-health
```

Or with Bash:

```bash
bash ./scripts/run-scenario.sh projects/example_inspection startup-health
```

To preserve a reproducible evidence pack for the run:

```powershell
.\scripts\run-scenario.ps1 projects\example_inspection startup-health -Evidence
```

```bash
bash ./scripts/run-scenario.sh projects/example_inspection startup-health --evidence
```

Evidence capture does not expand the scenario action schema or change its
inert safety boundary. See [`docs/EVIDENCE_PACKS.md`](EVIDENCE_PACKS.md).

To run the operator-gated example and capture its evidence:

```powershell
.\scripts\run-scenario.ps1 projects\example_inspection battery-failure `
    -AllowOperatorActions -Evidence
```

```bash
bash ./scripts/run-scenario.sh projects/example_inspection battery-failure \
  --allow-operator-actions --evidence
```

The runner:

1. Checks Docker, host storage, ports, and whether another `drn-stack` project
   is already running.
2. Builds the pinned DRN base image.
3. Validates the project and scenario inside that image.
4. Builds the project's derivative colcon-overlay image.
5. Starts the stack with the base and project Compose files merged.
6. Runs the existing full smoke test and project assertions.
7. For schema version 2 only, requires the operator flag, verifies that PX4 is
   disarmed, applies and measures the allowlisted failure, then verifies its
   restoration during cleanup.
8. Prints bounded logs on failure and always stops its containers.

When evidence is enabled, the runner also starts a topic-allowlisted MCAP
recording before the assertions, captures PX4's boot ULog, and finalizes a
checksummed verdict after the containers stop.

Images and Docker build cache are preserved. The runner never deletes global
Docker data.

## Required project layout

```text
my_project/
|-- Dockerfile
|-- compose.override.yaml
|-- project.yaml
|-- scenarios/
|   `-- startup-health.yaml
`-- ros_ws/
    `-- src/
        `-- my_ros_package/
```

The project directory may live inside or outside the DRN Stack checkout. The
wrappers set `DRN_PROJECT_DIR` to its absolute path. Compose resolves override
paths relative to DRN Stack's base `compose.yaml`, so project overrides should
use `${DRN_PROJECT_DIR}` for their build context and bind mount rather than
assuming paths are relative to `compose.override.yaml`.

Use [`projects/example_inspection`](../projects/example_inspection) as the
minimal working template.

## Project manifest

`project.yaml` has a strict, versioned schema:

```yaml
schema_version: 1
name: my-project
simulation:
  vehicle: gz_x500
  world: default
launch:
  package: my_ros_package
  file: my_project.launch.py
  arguments:
    parameter_file: /opt/drn_project/config/project.yaml
health:
  nodes:
    - /my_project_node
  topics:
    - /my_project/heartbeat
  services: []
scenarios:
  - startup-health
```

- `simulation.vehicle` becomes `PX4_SIM_MODEL`.
- `simulation.world` becomes `PX4_GZ_WORLD`.
- `launch` selects one ROS 2 launch file and typed launch arguments. Arguments
  are passed directly as `name:=value`; they are never evaluated by a shell.
- `health` lists exact ROS graph names expected from the project.
- `scenarios` is an allowlist of scenario filenames without `.yaml`.

Unknown fields, invalid names, undeclared scenarios, and duplicate values fail
closed. Project package names are compared with the DRN underlay; schema
version 1 permits new packages but rejects attempts to override installed core
packages.

The Compose override is also strict: it may replace only the `ros-viz` image
and build definition, set the fixed manifest location, and mount the project
read-only. Changes to PX4, ports, commands, privileges, devices, networks, or
other environment variables are rejected by the supported runner.

## Inert scenario schema

```yaml
schema_version: 1
name: startup-health
timeout_seconds: 480
setup:
  - type: core-smoke
actions: []
assertions:
  - type: project-health
  - type: topic-message
    name: /my_project/heartbeat
cleanup:
  - type: stop-stack
```

Version 1 accepts exactly:

- the existing disarmed `core-smoke` setup;
- an empty `actions` list;
- `project-health` assertions for manifest-declared nodes, topics, and
  services;
- `topic-message` assertions for topics already declared in project health;
- `stop-stack` cleanup.

The timeout covers the core smoke test and all project assertions. There is no
arbitrary command, script, service-call, or topic-publication primitive.

## Operator-gated failure schema

Schema version 2 is intentionally limited to one measurable, disarmed PX4 SITL
battery failure:

```yaml
schema_version: 2
name: battery-failure
timeout_seconds: 480
setup:
  - type: core-smoke
actions:
  - type: inject-failure
    component: battery
    failure_type: "off"
assertions:
  - type: project-health
  - type: topic-message
    name: /my_project/heartbeat
cleanup:
  - type: restore-failure
    component: battery
  - type: stop-stack
```

The runner rejects this schema unless PowerShell receives
`-AllowOperatorActions` or Bash receives `--allow-operator-actions`. The PX4
adapter independently requires its internal gate, confirms
`SYS_FAILURE_EN=1`, and refuses to inject unless PX4 reports the disarmed
arming state. A battery `off` action passes only after voltage falls to the
expected simulated-failure range. Cleanup always attempts `battery ok` and
passes only after normal voltage returns. The run also fails if PX4's
`armed_time` shows that it armed at any point during the scenario.

Version 2 does not accept GPS, motor, sensor, arbitrary PX4-shell, arming,
takeoff, movement, Land, RTL, or hardware actions. Additional primitives need
their own version-matched compatibility research, measurable effect assertion,
cleanup contract, and explicit review.

## Colcon overlay image

A project image derives from the pinned base image, builds new packages against
`/opt/drn_ws/install`, and copies its install space to
`/opt/drn_project_ws/install`. Set:

```dockerfile
ENV DRN_PROJECT_SETUP=/opt/drn_project_ws/install/setup.bash
```

The DRN entrypoint, health checks, smoke tests, and interactive `run` commands
then source the project overlay after the core underlay. The setup path is
restricted to that exact container location.

The project owns additional build and runtime dependencies in its derivative
Dockerfile. It must keep the final manifest available at
`/opt/drn_project/project.yaml`, normally through the read-only bind mount in
the example Compose override.

## Validation

Contract changes require:

```bash
bash ./scripts/lint.sh
bash ./scripts/test-ros-build.sh
bash ./scripts/run-scenario.sh projects/example_inspection startup-health
bash ./scripts/run-scenario.sh projects/example_inspection battery-failure \
  --allow-operator-actions --evidence
```

The startup-health command is the ordinary inert integration test. The battery
command is disarmed but explicitly operator-gated. Neither validates takeoff,
movement, Land, RTL, hardware, or in-flight failure recovery.
