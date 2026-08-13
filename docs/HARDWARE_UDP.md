# Hardware UDP companion profile

The `hardware-udp` connection profile is the first real-device scaffold for
DRN Stack. It runs the pinned ROS 2 workspace and Micro XRCE-DDS Agent against
one PX4 flight controller over a trusted IPv4 bench network. It does not start
PX4 SITL, Gazebo, `drn_control`, a downstream project, or any Foxglove publish
or service endpoint.

This profile is deliberately an acceptance rig, not a flight workflow. A run
passes only when the board reports the pinned PX4 v1.17.0 firmware and git
identity, the expected transport parameters are readable, the version-matched
ROS topics are live, and multiple status samples remain disarmed.

## Physical safety prerequisites

Before connecting or powering the board:

1. Remove all propellers. For a bench-only flight controller, disconnect the
   actuator power path as well.
2. Use an isolated or trusted wired network. Do not expose the XRCE-DDS or
   MAVLink UDP ports on Wi-Fi, a public interface, or `0.0.0.0`.
3. Flash the exact PX4 v1.17.0 build represented by commit
   `a5eb12d2ab591251faa009f76b2685b8cc64405d`.
4. Configure PX4 while DRN Stack is stopped. The DRN verifier reads parameters
   but never writes them, arms, changes mode, opens a shell, or reboots PX4.
5. Keep QGroundControl available on a separate link for configuration and an
   immediate independent view of the vehicle's arming state.

## Board and network configuration

The host/companion address used below is `10.41.10.1` only as an example. Use
the actual static address of the Ethernet adapter connected to the board.

Configure PX4's uXRCE-DDS client to use Ethernet, the companion address, and
UDP port `8888`:

- `UXRCE_DDS_CFG`: Ethernet
- `UXRCE_DDS_AG_IP`: the companion/host bench-interface address
- `UXRCE_DDS_PRT`: `8888`
- `UXRCE_DDS_DOM_ID`: the same domain as `ROS_DOMAIN_ID` (default `0`)

Configure MAVLink Ethernet instance 2 to send its Onboard stream to the same
companion address and UDP port `14580`. The verifier reads these parameters by
default:

- `MAV_2_CONFIG`
- `MAV_2_MODE`
- `MAV_2_REMOTE_PRT`
- `MAV_2_UDP_PRT`

Board layouts can assign another MAVLink instance. In that case, explicitly
set `DRN_HARDWARE_PARAMETERS` to the comma-separated `UXRCE_DDS_*` and
`MAV_<instance>_*` names that define the link. Missing parameters fail closed.
Parameter values are recorded in the acceptance report for review; the tool
does not attempt to decide board-specific enum values or correct them.

PX4's official [uXRCE-DDS setup](https://docs.px4.io/v1.17/en/middleware/uxrce_dds)
and [Ethernet setup](https://docs.px4.io/main/en/advanced_config/ethernet_setup)
remain authoritative for board configuration.

## Run the acceptance rig

Windows PowerShell:

```powershell
.\scripts\run-hardware.ps1 -BindAddress 10.41.10.1
```

Linux, Git Bash, or WSL:

```bash
bash ./scripts/run-hardware.sh --bind-address 10.41.10.1
```

The lifecycle script builds only `drn-stack/ros-viz:humble`, starts only the
`ros-viz` service, and then runs the acceptance check. It listens for incoming
PX4 traffic on:

- UDP `8888`: Micro XRCE-DDS Agent
- UDP `14580`: MAVLink identity and parameter verifier
- TCP `127.0.0.1:8765`: read-only Foxglove Bridge

The selected bind address must be a concrete non-loopback IPv4 address.
Wildcard binding is rejected. Host firewall rules should allow UDP `8888` and
`14580` only on that trusted interface and only from the board's address.

## Acceptance result

Each attempt writes `artifacts/hardware/hardware-udp-<UTC timestamp>.json`,
including failed attempts. A passing report contains:

- DRN git revision and ROS image ID;
- expected and observed PX4 semantic version and git identity;
- MAVLink system/component IDs and selected read-only parameter values;
- exact ROS topic types and disarmed telemetry sample timestamps;
- confirmation that no DRN control endpoints were present;
- the final `passed` or `failed` verdict.

Useful lifecycle commands use the same explicit bind address:

```powershell
.\scripts\hardwarectl.ps1 status -BindAddress 10.41.10.1
.\scripts\hardwarectl.ps1 logs -BindAddress 10.41.10.1
.\scripts\hardwarectl.ps1 stop -BindAddress 10.41.10.1
```

```bash
bash ./scripts/hardwarectl.sh status --bind-address 10.41.10.1
bash ./scripts/hardwarectl.sh logs --bind-address 10.41.10.1
bash ./scripts/hardwarectl.sh stop --bind-address 10.41.10.1
```

## Fail-closed behavior

The acceptance run fails when it sees the wrong autopilot, an armed heartbeat
or ROS status sample, more than one PX4 system ID, the wrong firmware version
or hash, missing transport parameters, mismatched ROS message types, stale
status/odometry, or any `/drn_control` or `/drn/control/*` endpoint.

The Foxglove bridge is observational only: both client publication and service
allowlists match nothing. This first slice does not support flight, actuator
testing, configuration writes, firmware updates, serial transport, multiple
vehicles, or automatic downstream-project launch.

## Physical validation still required

CI can validate the overlay, safety assertions, verifier logic, ROS build, and
all existing SITL profiles. Before declaring the hardware profile qualified,
an operator must run it on a propeller-free bench with the pinned board image,
review the JSON report, verify disconnect/reconnect failure behavior, and
independently confirm that no parameters or vehicle state changed.
