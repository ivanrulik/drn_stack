# Simulation profiles

DRN Stack ships four supported profiles on the current x500 airframe. The
profile contract itself is airframe-neutral: each directory declares its
airframe, PX4 model, capabilities, and spawned Gazebo model name. New airframes
can therefore reuse the lifecycle, safety, observation, and validation layers.

| Profile | PX4 model | ROS sensor output | Intended use |
| --- | --- | --- | --- |
| `x500-basic` | `gz_x500` | None | Flight-control and project-SDK baseline |
| `x500-depth` | `gz_x500_depth` | Color, metric depth, camera calibration | Perception, mapping, and avoidance development |
| `x500-vio` | `gz_x500_vision` | Simulated vision odometry | Localization integration and odometry consumers |
| `x500-lidar` | `gz_x500_lidar_2d` | 270-degree 2D laser scan | Mapping, obstacle sensing, and scan consumers |

Profiles are small Compose overrides under `profiles/`; the base topology,
network namespace, safety gates, and lifecycle behavior remain shared.

## Start and operate a profile

PowerShell:

```powershell
.\scripts\run-sim.ps1 -Profile x500-depth
.\scripts\status.ps1 -Profile x500-depth
.\scripts\restart.ps1 -Profile x500-depth
.\scripts\run-sim.ps1 -Profile x500-vio
.\scripts\run-sim.ps1 -Profile x500-lidar
```

Bash, Git Bash, or WSL:

```bash
bash ./scripts/run-sim.sh --profile x500-depth
bash ./scripts/status.sh --profile x500-depth
bash ./scripts/restart.sh --profile x500-depth
bash ./scripts/run-sim.sh --profile x500-vio
bash ./scripts/run-sim.sh --profile x500-lidar
```

Pass the profile again when restarting so Compose recreates the same model.
Stop commands work with the default arguments because all profiles use the
same `drn-stack` project and service names.

## Profile extension contract

The lifecycle scripts discover profiles from `profiles/<name>/compose.yaml`;
they do not contain an allowlist of vehicle names. Every profile sets these
values on `ros-viz`:

| Variable | Purpose |
| --- | --- |
| `DRN_PROFILE` | Stable profile identifier matching the directory name |
| `DRN_AIRFRAME` | Airframe family, currently `x500` |
| `DRN_PROFILE_CAPABILITIES` | Comma-separated runtime capabilities |
| `DRN_SIM_MODEL_NAME` | Spawned Gazebo model instance used to resolve topics |

The currently supported capabilities are `depth-camera`, `laser-scan`, and
`vision-odometry`. ROS launch behavior, health checks, and full smoke checks
select functionality by capability instead of by airframe name. A profile that
needs optional GPU rendering can provide matching `compose.gpu.yaml` and
`compose.software.yaml` files; the lifecycle scripts discover those files too.

Profile Compose files remain small overrides. They must not copy the base
topology or weaken inert startup, network namespace, Foxglove allowlists, or
operator gates.

## GPU acceleration

The lifecycle scripts run an EGL renderer probe in the pinned PX4 image whenever
`x500-depth` or `x500-lidar` starts or restarts. They add the NVIDIA GPU override
only when that probe initializes a hardware renderer and rejects Mesa software
rasterizers such as llvmpipe. A successful `nvidia-smi` check alone is not enough
because it can prove compute access without proving the OpenGL/EGL path Gazebo
uses.

When no hardware renderer is available, the depth software override changes
color from 1920 x 1080 at 30 Hz to 640 x 360 at 10 Hz and lowers depth from 30
to 15 Hz while preserving its 640 x 480 resolution. The LiDAR software override
preserves all 1,080 rays and lowers the scan rate from 30 to 10 Hz. Hardware
rendering retains the upstream resolutions and 30 Hz rates.

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
  probe fails. This is the supported and expected behavior for render-backed
  depth and LiDAR profiles.
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

## x500-vio ROS contract

The pinned PX4 `gz_x500_vision` model attaches Gazebo's 3D odometry publisher
to the x500 model. DRN bridges its covariance-bearing message and normalizes the
model-specific frame labels into this stable ROS contract:

| Topic | Type | Frames | Convention |
| --- | --- | --- | --- |
| `/drn/sensors/vision/odometry` | `nav_msgs/msg/Odometry` | `map` -> `base_link` | ENU world, FLU body |

This is deterministic, ground-truth-derived **simulated vision odometry**. It
does not process camera images or IMU measurements and is not a fidelity claim
for a real VIO estimator. It is useful for testing integrations that consume
odometry, frame conventions, covariance, timing, evidence capture, and
visualization before selecting a real estimator.

PX4's Gazebo bridge also receives the upstream odometry internally. DRN does
not change EKF2 fusion parameters, disable GPS, inject a second external
odometry publisher, or claim VIO-only position flight support. Those behaviors
remain separately researched and operator-validated work.

## x500-lidar ROS contract

The pinned PX4 `gz_x500_lidar_2d` model carries a Hokuyo-style rendered scanner
with 1,080 rays over 270 degrees and a 0.1 to 30 metre range. DRN bridges the
Gazebo scan through an internal topic, replaces the generic upstream `link`
frame label, and publishes this stable contract:

| Topic | Type | Frame | Convention |
| --- | --- | --- | --- |
| `/drn/sensors/lidar/scan` | `sensor_msgs/msg/LaserScan` | `lidar_link` | x-forward, y-left, counter-clockwise angles |
| `/drn/viz/lidar/walls` | `visualization_msgs/msg/MarkerArray` | `map` | Static visualization of the pinned `walls` world geometry |

The static `base_link -> lidar_link` transform is at the simulated sensor
origin. The profile deliberately does not republish the accompanying point
cloud, enable PX4 collision prevention, or add avoidance behavior. Consumers
that need a cloud can derive it from the scan without duplicating transport for
all users.

The profile selects PX4's pinned `walls` world by default so the stationary,
disarmed vehicle receives finite returns that are immediately visible in
Foxglove. Set `PX4_GZ_WORLD` before startup to deliberately select another
world; the full profile smoke expects obstacle returns and therefore targets
the default `walls` configuration.

## Foxglove

Connect to `ws://localhost:8765` and import
[`foxglove/drn-simulation-x500-depth.json`](../foxglove/drn-simulation-x500-depth.json).
The layout shows the vehicle, color image, and depth image. The depth panel uses
a Turbo color map over 0.2 to 10 metres. The normal control layout remains a
separate import, keeping this perception-focused view inert by default.

For `x500-vio`, import
[`foxglove/drn-simulation-x500-vio.json`](../foxglove/drn-simulation-x500-vio.json).
It shows the stable ENU position stream, complete odometry message, vehicle
status, and normal 3D view without adding flight controls.

For `x500-lidar`, import
[`foxglove/drn-simulation-x500-lidar.json`](../foxglove/drn-simulation-x500-lidar.json).
It renders the scan in the 3D view and provides raw scan and vehicle-status
inspection without adding flight controls. The default `walls` world produces
magenta scan points around the stationary vehicle without requiring an armed
flight or a separately spawned obstacle. Translucent blue markers reproduce the
four pinned wall collision boxes so the returns have visible scene context;
these markers are visualization only and do not create simulator geometry.

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

For `x500-vio`, the full smoke check requires three timestamp-distinct samples
with finite pose, twist, and covariance values; a normalized unit quaternion;
the stable `map` and `base_link` frames; and a current PX4 status reporting
disarmed. The upstream odometry publisher does not require camera rendering, so
the profile does not use the depth profile's GPU overrides.

For `x500-lidar`, the full smoke check requires three timestamp-distinct scans,
the 1,080-ray angular and range contract, valid finite or positive-infinite
ranges with finite obstacle returns, `base_link -> lidar_link` TF, and a current
PX4 status reporting disarmed.

### LiDAR resource gate

The gate was measured before implementation on 2026-08-10 using the pinned
images and Docker Desktop software rendering:

- PX4 image: 6,286,756,280 bytes (5.85 GiB). The pinned image already contains
  `x500_lidar_2d` and its sensor assets, so the profile adds no PX4 image layer.
- Cached no-build startup to both services healthy: 12.6 seconds.
- One post-start sample: `ros-viz` 135.1 MiB and `px4-sitl` 159.8 MiB; PX4/Gazebo
  used 26.7% CPU at the instant sampled.
- Recent complete Docker smoke runs before this profile took 22 to 28 minutes.
  The LiDAR CI step records its own startup time, image bytes, and container
  resource snapshot in the GitHub Actions job summary. Its startup remains
  bounded by the existing 300-second profile readiness limit.

The implemented profile was then measured on the same host and software path:

- PX4 remained 6,286,756,280 bytes; the ROS image was 1,073,727,590 bytes, an
  increase of 652,628 bytes over the pre-profile ROS image.
- A cached normal lifecycle run, including the EGL probe, health wait, and full
  inert smoke check, completed in 45 seconds.
- One scan-active sample used 214 MiB for `ros-viz` and 588.2 MiB for
  `px4-sitl`; instantaneous CPU was 8.56% and 260.80%, respectively.

These are routing measurements, not cross-host performance guarantees. Compare
future measurements on the same host and rendering mode; actual rates and CPU
load depend on subscribers and scene complexity.
