# Compatibility policy

DRN Stack supports one tested integration baseline at a time. The authoritative
Git revisions are the build arguments in [`compose.yaml`](../compose.yaml).
Human-readable version labels below describe those exact pins; they do not
authorize mixing other branches, tags, or message definitions.

## Supported baseline

| Component | Supported version | Authoritative source |
| --- | --- | --- |
| Host workflow | Windows PowerShell, Linux, Git Bash, or WSL with Docker Compose v2 | Repository lifecycle scripts |
| Container OS | Ubuntu 22.04 | `docker/Dockerfile.px4` and ROS base image |
| ROS 2 | Humble | `ros:humble-ros-base-jammy` |
| PX4-Autopilot | v1.17.0 | `a5eb12d2ab591251faa009f76b2685b8cc64405d` |
| `px4_msgs` | v1.17.0 definitions | `35a005a86b82cae28bd7a2eb58c4bb7a840830c9` |
| `px4_ros_com` | v1.17-compatible source | `86e9aeb20e55a4673fa8a9f1c29ea06a6c5ad1af` |
| PX4 ROS 2 Interface Library | `release/1.17` compatible source | `4a3370f084ac6f1ef001a4afa2b007845ffd0837` |
| Micro XRCE-DDS Agent | v2.4.3 | `73622810d984349b80bbac0ef55fc0b694d62222` |
| Gazebo | Harmonic packages selected by the pinned PX4 setup | PX4 image build |
| ROS-Gazebo bridge | Harmonic 0.244.12 (`ROS_GZ_HARMONIC_VERSION: 0.244.12-3jammy`) | OSRF Ubuntu stable repository |
| Foxglove Bridge | ROS Humble package resolved at image build time | ROS image build |

Git-based dependencies are pinned to immutable commits. The ROS base image and
APT packages are distribution-pinned but not digest-pinned, so rebuilding on a
later date can include compatible upstream package updates. DRN Stack aims for
a repeatable supported environment, not byte-for-byte identical container
images.

## Compatibility rules

- The PX4 firmware, `px4_msgs`, `px4_ros_com`, and PX4 ROS 2 Interface Library
  pins are one compatibility unit.
- `main` and tagged DRN Stack releases support only the combination documented
  at their own revision.
- Alternate upstream versions are experimental unless a branch explicitly
  documents and validates them.
- WSL may host the Bash lifecycle workflow, but WSLg/Mesa D3D12 graphics
  bridging is not part of the supported simulation baseline. Windows Docker
  Desktop falls back to the balanced software sensor configuration when its
  EGL hardware probe fails.
- Dependency pins must not be updated incidentally.
- A pin update requires release notes and issue review for message, transport,
  mode-registration, executor, watchdog, and failsafe compatibility.
- Hardware profiles must fail closed when firmware identity, transport, or
  message compatibility cannot be confirmed.

## Validation for baseline changes

A proposed baseline change must pass:

```bash
bash ./scripts/lint.sh
bash ./scripts/test-ros-build.sh
bash ./scripts/run-sim.sh
bash ./scripts/status.sh
docker compose --project-name drn-stack exec -T ros-viz \
  /usr/local/bin/drn-smoke-test full
```

Control, hardware, or moving-vehicle changes also require focused tests and
explicit operator-in-the-loop validation. Automated validation must remain
disarmed and motionless.

Known upstream constraints remain documented in
[`src/drn_control/README.md`](../src/drn_control/README.md).
