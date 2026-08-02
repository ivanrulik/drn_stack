# Scenario evidence packs

DRN Stack can preserve an inert project-scenario run as a portable evidence
pack for diagnosis, comparison, and CI failure review. Capture is opt-in and
does not add any scenario action, arm the vehicle, activate a flight mode, or
publish a control command.

## Capture

Run the Phase 1 scenario contract with evidence enabled:

```powershell
.\scripts\run-scenario.ps1 projects\example_inspection startup-health -Evidence
```

```bash
bash ./scripts/run-scenario.sh projects/example_inspection startup-health --evidence
```

The runner creates `artifacts/<run-id>/`, starts the existing isolated stack,
records telemetry around the scenario assertions, stops the recorder with
`SIGINT`, captures bounded logs, gracefully stops PX4 so its ULog is complete,
and finally writes and validates the evidence manifest. A failed scenario still
attempts to preserve a failed, possibly partial pack.

PX4 v1.17 SITL already logs from boot. DRN bind-mounts only that run's
`build/px4_sitl_default/rootfs/log` directory, so the collected `.ulg` belongs
to the current isolated stack rather than a previous container.

## Contents

```text
artifacts/<run-id>/
|-- manifest.json
|-- result.json
|-- logs/
|   |-- compose.log
|   |-- rosbag-info.txt
|   |-- rosbag-record.log
|   `-- scenario.log
|-- metadata/
|   |-- compose.yaml
|   |-- project.yaml
|   `-- scenario.yaml
|-- state/
|   `-- recorder.json
|-- telemetry/
|   |-- metadata.yaml
|   `-- telemetry_0.mcap
`-- ulog/
    `-- <date>/<time>.ulg
```

`manifest.json` records the DRN Git revision, pinned upstream refs, project and
scenario, selected vehicle/world/domain, image tags and immutable image IDs,
the topic allowlist, capture limits, timestamps, final verdict, file sizes,
and SHA-256 checksums. `result.json` is the small machine-readable verdict.
The captured project/scenario definitions make the assertions reviewable even
without the original checkout.

MCAP uses the ROS 2 `mcap` storage plugin with the `zstd_fast` profile, which
keeps chunk indexes available for selective reading and Foxglove replay. The
allowlist contains core PX4 state, clock, TF/model topics, and the project's
declared health topics; it never records all ROS traffic implicitly.
Finalization fails a nominally passing run if the bag contains no messages.

## Bounds and retention

- MCAP files split at 256 MiB.
- Scenario duration is already bounded by the project contract at 600 seconds.
- A successful pack must stay under 1 GiB or the run fails evidence validation.
- Compose capture is limited to the newest 500 log lines.
- Local retention keeps five recognized finalized packs by default.
- CI artifacts are retained for seven days.

Only directories with a valid `drn.evidence/v1` manifest and a matching run ID
are eligible for automatic local pruning. Unknown directories and files under
`artifacts/` are left untouched.

The local limits can be tightened for an intentional run:

```powershell
$env:DRN_EVIDENCE_MAX_BYTES = '536870912'
$env:DRN_EVIDENCE_RETENTION_COUNT = '3'
```

```bash
export DRN_EVIDENCE_MAX_BYTES=536870912
export DRN_EVIDENCE_RETENTION_COUNT=3
```

`DRN_EVIDENCE_ROOT` can select another host directory. Normal stack stop and
restart commands do not delete evidence packs.

## Replay

Replay publishes the recorded MCAP through a read-only Foxglove bridge bound
to localhost. It does not start PX4, Gazebo, `drn_control`, or the project
scenario:

```powershell
.\scripts\replay.ps1 artifacts\<run-id>
```

```bash
bash ./scripts/replay.sh artifacts/<run-id>
```

Open Foxglove at `ws://localhost:8765` while the command is running. The replay
helper verifies every checksum before publishing and exits when the bag ends.
Its bridge rejects all client publications and service calls.

The default replay image is `drn-stack/ros-viz:humble`. If a project recorded
custom message types, pass the project image as the second argument:

```powershell
.\scripts\replay.ps1 artifacts\<run-id> drn-stack/example-inspection:humble
```

```bash
bash ./scripts/replay.sh artifacts/<run-id> drn-stack/example-inspection:humble
```

ULog remains the authoritative PX4-native record and can be inspected with
PX4-compatible analysis tools. This first slice does not run PX4 system-wide
ULog replay or failure injection.
