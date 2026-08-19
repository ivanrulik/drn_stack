# Simulation profiles

DRN Stack ships six supported profiles on the current x500 airframe. The
profile contract itself is airframe-neutral: each directory declares its
airframe, PX4 model, capabilities, and spawned Gazebo model name. New airframes
can therefore reuse the lifecycle, safety, observation, and validation layers.

| Profile | PX4 model | ROS sensor output | Intended use |
| --- | --- | --- | --- |
| `x500-basic` | `gz_x500` | None | Flight-control and project-SDK baseline |
| `x500-depth` | `gz_x500_depth` | Color, metric depth, camera calibration | Perception, mapping, and avoidance development |
| `x500-vio` | `gz_x500_vision` | Simulated vision odometry | Localization integration and odometry consumers |
| `x500-lidar` | `gz_x500_lidar_2d` | 270-degree 2D laser scan | Mapping, obstacle sensing, and scan consumers |
| `x500-precision-land` | `gz_x500_mono_cam_down` | Downward image, calibration, ArUco target pose | Operator-gated precision landing in SITL |
| `x500-multi` | Two to four `gz_x500` instances | Namespaced PX4 telemetry | Fleet namespace, routing, TF, and observation tests |

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
.\scripts\run-sim.ps1 -Profile x500-precision-land
.\scripts\run-sim.ps1 -Profile x500-multi
.\scripts\run-sim.ps1 -Profile x500-multi -VehicleCount 4
```

Bash, Git Bash, or WSL:

```bash
bash ./scripts/run-sim.sh --profile x500-depth
bash ./scripts/status.sh --profile x500-depth
bash ./scripts/restart.sh --profile x500-depth
bash ./scripts/run-sim.sh --profile x500-vio
bash ./scripts/run-sim.sh --profile x500-lidar
bash ./scripts/run-sim.sh --profile x500-precision-land
bash ./scripts/run-sim.sh --profile x500-multi
bash ./scripts/run-sim.sh --profile x500-multi --vehicle-count 4
```

Pass the profile again when restarting so Compose recreates the same model. For
`x500-multi`, also repeat `-VehicleCount` or `--vehicle-count` when the fleet is
larger than the default two. Stop commands work with the default arguments
because all profiles use the same `drn-stack` project and service names.

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

The currently supported capabilities are `depth-camera`, `laser-scan`,
`multi-vehicle`, `precision-landing`, and `vision-odometry`. ROS launch behavior, health checks, and
full smoke checks
select functionality by capability instead of by airframe name. A profile that
needs optional GPU rendering can provide matching `compose.gpu.yaml` and
`compose.software.yaml` files; the lifecycle scripts discover those files too.

Profile Compose files remain small overrides. They must not copy the base
topology or weaken inert startup, network namespace, Foxglove allowlists, or
operator gates.

## GPU acceleration

The lifecycle scripts run an EGL renderer probe in the pinned PX4 image whenever
`x500-depth`, `x500-lidar`, or `x500-precision-land` starts or restarts. They add the NVIDIA GPU override
only when that probe initializes a hardware renderer and rejects Mesa software
rasterizers such as llvmpipe. A successful `nvidia-smi` check alone is not enough
because it can prove compute access without proving the OpenGL/EGL path Gazebo
uses.

When no hardware renderer is available, the depth software override changes
color from 1920 x 1080 at 30 Hz to 640 x 360 at 10 Hz and lowers depth from 30
to 15 Hz while preserving its 640 x 480 resolution. The LiDAR software override
preserves all 1,080 rays and lowers the scan rate from 30 to 10 Hz. Hardware
rendering retains the upstream resolutions and 30 Hz rates.

The precision-landing software override lowers the downward camera from
1280 x 960 at 30 Hz to 640 x 480 at 15 Hz without changing its field of view.

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

## x500-precision-land ROS contract

The profile uses PX4's pinned `gz_x500_mono_cam_down` model and `aruco` world.
The detector is derived from the useful perception portion of ARK Electronics'
[Tracktor Beam](https://github.com/ARK-Electronics/tracktor-beam) example, but
is integrated into DRN's stable topics, pinned ROS image, official PX4 mode
executor, and safety gates.

| Topic | Type | Contract |
| --- | --- | --- |
| `/drn/sensors/landing/image_raw` | `sensor_msgs/msg/Image` | Downward camera image from Gazebo |
| `/drn/sensors/landing/camera_info` | `sensor_msgs/msg/CameraInfo` | Matching camera intrinsics |
| `/drn/sensors/landing/visible` | `std_msgs/msg/Bool` | Detector heartbeat and current visibility |
| `/drn/sensors/landing/target_pose` | `geometry_msgs/msg/PoseStamped` | Marker `0` relative pose in `landing_camera_optical` |
| `/drn/sensors/landing/debug/image` | `sensor_msgs/msg/Image` | Annotated observation image |

The detector uses OpenCV dictionary `DICT_4X4_250`, marker ID `0`, and a
0.5-metre marker matching the pinned PX4 world. The controller converts the
optical-frame target through body FRD into PX4 NED, aligns horizontally,
requires a bounded alignment dwell, and then descends at a limited rate. It
pauses descent to realign, hands off the final 0.6 metres to PX4 Land, and
returns to Hold when the target becomes stale. It does not search for a target.

Precision landing is never automatic. The operator must activate DRN Control,
request takeoff, confirm a current target, and call
`/drn/control/precision_land`. Hold, Land, RTL, and
`/drn/control/precision_land/abort` preempt the sequence. These armed steps are
operator-in-the-loop SITL checks and are not part of automated smoke testing.

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

For `x500-precision-land`, import
[`foxglove/drn-simulation-x500-precision-land.json`](../foxglove/drn-simulation-x500-precision-land.json).
It shows the annotated downward image, target pose, control status, and TF
context without adding Teleop controls.

For `x500-multi`, import
[`foxglove/drn-simulation-x500-multi.json`](../foxglove/drn-simulation-x500-multi.json).
It shows every supported x500 slot under `map`, separate NED position plots,
and raw status inspection. Unused slots remain empty when fewer than four are
requested. Its Foxglove publication and service allowlists match nothing, so
the layout is observation-only.

## x500-multi fleet contract

The fleet profile supports an explicit count from two through four plain x500
instances and defaults to two. It shares one Gazebo server, one ROS service,
and one Micro XRCE-DDS Agent while assigning every PX4 instance a unique DDS
key, MAVLink system ID, model name, spawn pose, and ROS namespace:

| Vehicle | Spawn pose | ROS namespace | TF chain |
| --- | --- | --- | --- |
| `x500_1` | `(0, 0)` | `/px4_1` | `map -> px4_1/map -> px4_1/base_link` |
| `x500_2` | `(0, 2)` | `/px4_2` | `map -> px4_2/map -> px4_2/base_link` |
| `x500_3` | `(2, 0)` | `/px4_3` | `map -> px4_3/map -> px4_3/base_link` |
| `x500_4` | `(2, 2)` | `/px4_4` | `map -> px4_4/map -> px4_4/base_link` |

The full smoke check requires three fresh odometry and status samples from each
requested namespace, every vehicle continuously disarmed, every TF chain, no
unnamespaced `/fmu/*` topics, and no `/drn_control` or `/drn/control/*`
endpoints. Downstream-project launch is disabled in this profile.

This slice does not support fleet control, Teleop, arming, takeoff, mixed
airframes, sensor profiles, hardware, or more than four vehicles. Counts above
four fail before Compose startup instead of attempting an unqualified load.

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

For `x500-precision-land`, the full smoke check requires camera images,
calibration, detector visibility heartbeats, the landing-camera TF, both
precision-landing services, and a current PX4 status reporting disarmed. A pose
is validated when the marker is visible, but positive detection is not required
while the vehicle is sitting on the marker at its inert spawn height.

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

### Bounded fleet resource gate

The fixed `x500-multi` slice was measured on 2026-08-13 using the pinned images
and Docker Desktop software rendering on the same 32 GB Windows host:

- A cached PowerShell lifecycle run, including image checks, startup, health
  waits, and the full inert fleet smoke test, completed in 40.1 seconds.
- Three sustained post-start samples used 152.3 to 153.1 MiB for `ros-viz` and
  166.4 to 166.6 MiB for `px4-sitl`, or about 319 MiB combined.
- Instantaneous CPU was 6.23% to 7.49% for `ros-viz` and 265.47% to 266.66% for
  the container holding both PX4 instances and Gazebo. Docker percentages can
  exceed 100% because work spans multiple logical CPU cores.
- Five Gazebo samples reported a real-time factor from 0.9996 to 1.0000 while
  both independently identified PX4 instances remained connected and disarmed.

For comparison, a same-host `x500-basic` lifecycle completed in 29 seconds and
one post-start sample used about 388 MiB combined at roughly 164% combined CPU.
The fleet container uses direct PX4 instance launches instead of retaining the
single-profile build wrapper processes, so its lower sampled memory is not a
claim that two vehicles inherently require less memory. These are routing
measurements, not cross-host performance guarantees.

The bounded-count extension retains that two-vehicle regression and adds a
four-vehicle maximum-load run to Docker CI. Both paths must reach healthy within
300 seconds, pass fresh telemetry/disarmed/TF/isolation checks, and record CPU,
memory, process count, and startup time. Three vehicles use the same generated
identity and 2-by-2 spawn-grid path and remain covered by unit validation.

The expanded paths were qualified on 2026-08-14 on the same 32 GB Windows host:

- Three vehicles completed a cached stop/recreate/readiness/full-smoke lifecycle
  in 52.8 seconds. Three sustained samples used 389.9 to 390.5 MiB combined and
  3.64 to 3.77 logical CPU cores; Gazebo real-time factor remained 0.9999 to
  1.0003.
- Four vehicles completed the same lifecycle in 63.9 seconds. Three sustained
  samples used 467.9 to 468.7 MiB combined. PX4 and Gazebo used 6.15 to 6.98
  logical CPU cores while ROS used 0.15 to 0.63; combined peak use was 7.24
  cores. Gazebo real-time factor remained 0.9992 to 1.0007.
- Both expanded counts passed exact process/model/identity checks, three fresh
  odometry and status samples per namespace, continuous disarmed state, all TF
  chains, and the absence of unscoped PX4 or DRN control endpoints.

Four remains the fail-closed maximum because it is the highest count qualified
on both the local 16-CPU Docker allocation and the repository CI path. Raising
the cap requires a separate resource baseline and review.
