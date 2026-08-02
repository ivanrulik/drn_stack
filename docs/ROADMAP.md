# Open-source Ecosystem Roadmap

Last reviewed: 2026-08-02

## Purpose

DRN Stack already provides a reproducible PX4 v1.17, ROS 2 Humble, Gazebo
Harmonic, and Foxglove development environment. The next stage is to make it a
reusable testbed that other open-source drone projects can extend without
forking its core simulation and lifecycle code.

Priorities are ranked by:

1. Value to downstream drone and ROS 2 projects.
2. Fit with the existing reproducible Docker workflow.
3. Differentiation from PX4, QGroundControl, MAVSDK, and broader autonomy
   frameworks.
4. Implementation and long-term maintenance risk.

## Ranked features

| Rank | Feature | Score | Intended outcome |
| --- | --- | --- | --- |
| 1 | Pluggable project and scenario SDK | 9.4/10 | Downstream projects can add ROS 2 packages and validation scenarios without changing DRN Stack internals. |
| 2 | Reproducible flight evidence packs | 8.9/10 | Each experiment can produce a portable, replayable record of software versions, parameters, telemetry, and logs. |
| 3 | Vehicle, world, and sensor profiles | 8.6/10 | Perception, VIO, mapping, and avoidance projects can select a supported simulation profile instead of rebuilding the environment. |
| 4 | SITL-to-hardware companion profile | 8.1/10 | The same ROS 2 application can connect safely to SITL or bench hardware through an explicit transport profile. |
| 5 | Namespaced multi-vehicle test profile | 7.5/10 | Fleet projects can launch and observe isolated PX4 instances with stable namespaces and identities. |

## 1. Pluggable project and scenario SDK

### Goal

Turn DRN Stack from a fixed x500 workspace into a reusable development and
validation platform.

### Proposed first release

- Define a documented extension contract for adding an external ROS 2 package
  through a Compose override or mounted colcon overlay.
- Add a declarative project manifest that selects the vehicle, world,
  parameters, launch files, and expected health signals.
- Add scenario definitions for setup, operator actions, assertions, timeouts,
  and cleanup.
- Keep ordinary startup and automated smoke tests inert.
- Require an explicit operator gate for scenarios that arm or move a vehicle.
- Provide one small example project outside the core `drn_control` package.

Example structure:

```text
projects/example_inspection/
|-- project.yaml
|-- compose.override.yaml
|-- scenarios/
|   |-- startup-health.yaml
|   |-- command-loss-hold.yaml
|   `-- gps-loss.yaml
|-- assertions/
`-- foxglove/
```

Potential interface:

```powershell
.\scripts\run-scenario.ps1 projects/example_inspection startup-health
```

This work should build on PX4's simulation-based integration-testing model
rather than creating another flight-control state machine.

## 2. Reproducible flight evidence packs

### Goal

Make simulation results easy to reproduce, diagnose, compare, and attach to an
issue or pull request.

### Proposed contents

- ROS 2 telemetry recorded as MCAP for indexed Foxglove replay.
- PX4 ULog files.
- PX4 parameters and selected environment configuration.
- Git revisions and container image identifiers for all pinned components.
- Scenario definition, timestamps, assertions, and final verdict.
- Bounded container logs and a concise machine-readable summary.

Delivered first-slice interface:

```powershell
.\scripts\run-scenario.ps1 projects\example_inspection startup-health -Evidence
.\scripts\replay.ps1 artifacts\<run-id>
```

Evidence collection must use bounded retention so it does not undo the
repository's Docker and WSL storage safeguards.

## 3. Vehicle, world, and sensor profiles

### Goal

Support autonomy and perception development in addition to basic vehicle
control.

### Initial profiles

- `x500-basic`: current lightweight baseline.
- `x500-depth`: forward-facing depth camera.
- `x500-vio`: simulated vision odometry.
- `x500-lidar`: ROS 2 laser or point-cloud output.

Each profile should own its:

- PX4 model and Gazebo world selection.
- Gazebo-to-ROS topic bridge configuration.
- TF and frame conventions.
- Resource requirements and health checks.
- Foxglove layout additions.
- Focused lint and smoke assertions.

Profiles should remain declarative and composable. Avoid copying complete
Compose files for every model.

## 4. SITL-to-hardware companion profile

### Goal

Reduce the gap between a ROS 2 application validated in simulation and the same
application running against PX4 flight-controller hardware.

### Proposed scope

- Explicit `sitl`, `hardware-udp`, and `hardware-serial` connection profiles.
- Serial-device discovery and Docker device passthrough where supported.
- Firmware identity and message-version compatibility checks.
- Parameter snapshot and communication health report.
- A no-arm bench smoke test with clear physical safety prerequisites.
- Documentation for handing deeper board qualification to PX4's upstream bench
  tooling instead of duplicating it.

Hardware access must never be selected implicitly. Real-device profiles should
fail closed when identity, transport, or compatibility checks are incomplete.

## 5. Namespaced multi-vehicle test profile

### Goal

Provide reproducible fleet simulation infrastructure without prematurely
building a general swarm-autonomy framework.

### Proposed scope

- Generate a requested number of PX4 instances with unique instance numbers,
  DDS keys, MAVLink system IDs, ROS namespaces, and spawn poses.
- Publish isolated TF trees and stable vehicle identifiers.
- Provide fleet health reporting and a multi-vehicle Foxglove layout.
- Add non-arming namespace, routing, and isolation tests.

The first implementation should focus on simulation, observation, and routing.
PX4 supports multiple ROS 2 clients through one XRCE-DDS agent, but the
version-matched external-mode interface still has open multi-vehicle executor
behavior to resolve or work around. Fleet control should not be declared
supported until that behavior is validated.

## Delivery order

### Phase 0: Open-source adoption foundation

Status: complete.

- [x] Add a root license file matching the package metadata.
- [x] Replace placeholder maintainer addresses and normalize package versions.
- [x] Add contribution, support, and security guidance.
- [x] Define the compatibility and release policy for pinned upstream
  components.

### Phase 1: Extension contract

Status: complete.

- [x] Deliver the project manifest, Compose/colcon extension path, and inert
  scenario runner.
- [x] Publish one minimal downstream-project example.

### Phase 2: Evidence and regression workflow

Status: complete.

- [x] Add MCAP and ULog collection, metadata manifests, replay, bounded
  retention, and CI artifact publishing.
- [x] Add a disarmed, measurable battery-failure primitive with an explicit
  operator gate and verified restoration. Additional in-flight failure modes
  remain separate operator-in-the-loop work.

### Phase 3: Perception profiles

- Deliver depth-camera and VIO profiles first.
- Add LiDAR only after measuring image size, startup time, and CI resource cost.

### Phase 4: Hardware parity

- Add explicit UDP and serial companion profiles and no-arm bench validation.

### Phase 5: Multi-vehicle

- Deliver namespaced simulation and observation.
- Gate fleet control on focused upstream compatibility research and
  operator-in-the-loop validation.

## Strategic boundaries

DRN Stack should not attempt to become:

- Another ground-control station.
- A replacement for PX4's mode registration, acknowledgements, watchdogs, or
  failsafes.
- A general autonomous mission or swarm framework.
- A system that arms or moves a vehicle during ordinary startup or smoke tests.

Its useful niche is the reproducible layer where open-source drone applications
are integrated, observed, diagnosed, and validated across developer machines,
CI, and eventually bench hardware.

## Upstream references

- [PX4 integration testing](https://docs.px4.io/main/en/test_and_ci/integration_testing)
- [PX4 failure injection](https://docs.px4.io/main/en/debug/failure_injection)
- [PX4 Gazebo simulation](https://docs.px4.io/v1.17/en/sim_gazebo_gz/index)
- [PX4 multi-vehicle simulation with ROS 2](https://docs.px4.io/main/en/ros2/multi_vehicle)
- [PX4 uXRCE-DDS transport](https://docs.px4.io/main/en/middleware/uxrce_dds)
- [PX4 hardware bench testing](https://docs.px4.io/main/en/test_and_ci/bench_testing)
- [ROS 2 MCAP storage plugin](https://docs.ros.org/en/ros2_packages/humble/api/rosbag2_storage_mcap/)
- [Gazebo ROS 2 integration](https://gazebosim.org/docs/harmonic/ros2_integration/)
- [PX4 ROS 2 interface multi-vehicle issue](https://github.com/Auterion/px4-ros2-interface-lib/issues/191)
- [Aerostack2](https://github.com/aerostack2/aerostack2)
