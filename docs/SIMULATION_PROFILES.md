# Simulation profiles

DRN Stack ships two supported x500 profiles. The default remains the lightweight
`x500-basic` vehicle. `x500-depth` adds the camera model and the ROS-Gazebo
bridge needed for perception work without changing PX4, ROS, or Gazebo pins.

| Profile | PX4 model | ROS sensor output | Intended use |
| --- | --- | --- | --- |
| `x500-basic` | `gz_x500` | None | Flight-control and project-SDK baseline |
| `x500-depth` | `gz_x500_depth` | Color, metric depth, camera calibration | Perception, mapping, and avoidance development |

Profiles are small Compose overrides under `profiles/`; the base topology,
network namespace, safety gates, and lifecycle behavior remain shared.

## Start and operate a profile

PowerShell:

```powershell
.\scripts\run-sim.ps1 -Profile x500-depth
.\scripts\status.ps1 -Profile x500-depth
.\scripts\restart.ps1 -Profile x500-depth
```

Bash, Git Bash, or WSL:

```bash
bash ./scripts/run-sim.sh --profile x500-depth
bash ./scripts/status.sh --profile x500-depth
bash ./scripts/restart.sh --profile x500-depth
```

Pass the profile again when restarting so Compose recreates the same model.
Stop commands work with the default arguments because both profiles use the
same `drn-stack` project and service names.

## GPU acceleration

The lifecycle scripts run an EGL renderer probe in the pinned PX4 image whenever
`x500-depth` starts or restarts. They add the NVIDIA GPU override only when that
probe initializes a hardware renderer and rejects Mesa software rasterizers
such as llvmpipe. A successful `nvidia-smi` check alone is not enough because it
can prove compute access without proving the OpenGL/EGL path Gazebo uses.

When no hardware renderer is available, the software override changes color
from 1920 x 1080 at 30 Hz to 640 x 360 at 10 Hz and lowers depth from 30 to
15 Hz while preserving its 640 x 480 resolution. Hardware rendering retains
the upstream resolutions and 30 Hz rates.

Set `DRN_GPU_MODE` to control that behavior:

| Value | Behavior |
| --- | --- |
| `auto` | Use NVIDIA after a hardware EGL probe; otherwise use balanced software rates |
| `on` | Require a hardware EGL renderer and fail before startup when unavailable |
| `off` | Skip the probe and force balanced software rendering |

PowerShell example:

```powershell
$env:DRN_GPU_MODE = "on"
.\scripts\run-sim.ps1 -Profile x500-depth
```

Docker Desktop must have GPU support enabled and current NVIDIA drivers. On
Windows, Docker GPU compute access may still lack the graphics integration
required by Gazebo; `auto` detects that case and falls back cleanly. GPU
acceleration applies to Gazebo rendering only; the ROS bridge remains in the
`ros-viz` service.

### Supported host policy

- Windows with Docker Desktop uses the balanced software path when the EGL
  probe fails. This is the supported and expected `x500-depth` behavior.
- Native Linux may use NVIDIA headless EGL when the same probe confirms a
  hardware renderer. No manual driver-library injection is required or
  supported.
- WSL remains a supported shell for the lifecycle scripts, but WSLg graphics
  bridging is not a supported rendering profile. Making it work requires an
  additional Linux distribution, WSLg-specific device and library mounts, and
  Mesa D3D12 configuration. That increases the host matrix and has had upstream
  Gazebo camera and depth-rendering compatibility issues.

The project therefore does not ship or maintain a WSLg Compose override. Keep
any WSLg/D3D12 experiments out of the normal lifecycle path and require the
renderer probe plus the complete sensor smoke test before evaluating them. See
Microsoft's [WSLg container vGPU requirements][wslg-containers] and the Gazebo
[WSLg camera issue][gazebo-wslg-camera] for the underlying constraints.

[wslg-containers]: https://github.com/microsoft/wslg/blob/main/samples/container/Containers.md
[gazebo-wslg-camera]: https://github.com/gazebosim/gz-sim/issues/920

## x500-depth ROS contract

The profile converts the pinned PX4 model's Gazebo transport topics to stable
ROS 2 names:

| Topic | Type | Contract |
| --- | --- | --- |
| `/drn/sensors/front/color/image_raw` | `sensor_msgs/msg/Image` | 1920 x 1080 hardware or 640 x 360 software RGB image |
| `/drn/sensors/front/color/camera_info` | `sensor_msgs/msg/CameraInfo` | Matching color-camera intrinsics |
| `/drn/sensors/front/depth/image_raw` | `sensor_msgs/msg/Image` | 640 x 480 `32FC1` depth in metres |
| `/drn/sensors/front/depth/camera_info` | `sensor_msgs/msg/CameraInfo` | Matching depth-camera intrinsics |

All four messages retain the upstream `camera_link` frame ID. DRN publishes
that frame at the camera sensor origin with the REP-103 z-forward optical
orientation, producing a usable `base_link -> camera_link` transform without
copying high-bandwidth images through a relay. The bridge resolves the color
topics using `PX4_GZ_WORLD`; the default world remains `default`.

The Gazebo point-cloud topic is deliberately not bridged in this first slice.
Consumers should derive a cloud from the depth image and calibration when they
need one, avoiding duplicate high-bandwidth transport for projects that do not.

## Foxglove

Connect to `ws://localhost:8765` and import
[`foxglove/drn-simulation-x500-depth.json`](../foxglove/drn-simulation-x500-depth.json).
The layout shows the vehicle, color image, and depth image. The depth panel uses
a Turbo color map over 0.2 to 10 metres. The normal control layout remains a
separate import, keeping this perception-focused view inert by default.

## Validation and resource expectations

The normal full smoke check remains inert. For `x500-depth` it additionally
requires:

- three valid color/depth images and matching calibration samples;
- positive dimensions, complete image buffers, expected encodings, and matched
  optical frame IDs;
- the camera transform chain;
- a current PX4 status reporting disarmed.

Headless camera rendering consumes more CPU, memory, and shared-memory bandwidth
than `x500-basic`. Use the basic profile when sensor data is unnecessary. The
profile supports both NVIDIA-accelerated and balanced software headless
rendering. Hardware mode uses the upstream resolutions and 30 Hz sensor rates;
software mode uses 640 x 360 color at 10 Hz and 640 x 480 depth at 15 Hz.
Actual delivered rates still depend on the Docker host and camera subscribers.
