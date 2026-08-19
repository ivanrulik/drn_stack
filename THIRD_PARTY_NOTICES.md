# Third-party notices

DRN Stack is licensed under the MIT License except for the third-party
materials identified below. Dependencies downloaded while building the
containers remain under their respective upstream licenses.

## pymavlink

The ROS image installs `pymavlink` 2.4.49 from PyPI for read-only MAVLink
identity and parameter inspection in the hardware acceptance rig. pymavlink is
distributed under the GNU Lesser General Public License v3 or later; generated
MAVLink source is available under the MIT License. See the
[`pymavlink` project page](https://pypi.org/project/pymavlink/2.4.49/).
Its pinned `fastcrc` 0.3.6 dependency is distributed under the MIT License;
see the [`fastcrc` project page](https://pypi.org/project/fastcrc/0.3.6/).

## PX4 x500 model assets

The following files under `src/drn_viz/meshes/` come from the
[`PX4/PX4-gazebo-models`](https://github.com/PX4/PX4-gazebo-models)
`x500_base` model:

- `1345_prop_ccw.stl`
- `1345_prop_cw.stl`
- `5010Base.dae`
- `5010Bell.dae`
- `CF.png`
- `NXP-HGD-CF.dae`

The files were verified against upstream commit
[`e00d3b9cde682dbcb3bf6f30a2f2b8ef4325dae8`](https://github.com/PX4/PX4-gazebo-models/tree/e00d3b9cde682dbcb3bf6f30a2f2b8ef4325dae8/models/x500_base).
The DAE files in this repository use different line endings but otherwise
match that source.

These assets are distributed under the BSD-3-Clause license, copyright
Rudis Laboratories. A copy of that license is installed with the assets at
`src/drn_viz/meshes/LICENSE`.

## PX4 OakD-Lite sensor model

`profiles/x500-depth/models/OakD-Lite/model.sdf` is derived from the OakD-Lite
model in `PX4/PX4-Autopilot` at pinned commit
`a5eb12d2ab591251faa009f76b2685b8cc64405d`. DRN changes only the color
resolution and the color/depth update rates used by the software-rendering
fallback. PX4-Autopilot is distributed under the BSD-3-Clause license.

## PX4 2D LiDAR sensor model

`profiles/x500-lidar/models/lidar_2d_v2/model.sdf` is derived from the
`lidar_2d_v2` model in `PX4/PX4-gazebo-models` at the PX4-pinned submodule
commit `b6127f4ec20de867e215fb5f78ae88b80f371909`. DRN changes only the update
rate used by the software-rendering fallback. PX4-gazebo-models is distributed
under the BSD-3-Clause license.

## PX4 downward monocular camera model

`profiles/x500-precision-land/models/mono_cam/model.sdf` is derived from the
`mono_cam` model in `PX4/PX4-gazebo-models` at the PX4-pinned submodule commit
`b6127f4ec20de867e215fb5f78ae88b80f371909`. DRN changes only the image
resolution and update rate used by the software-rendering fallback.
PX4-gazebo-models is distributed under the BSD-3-Clause license.

## ARK Electronics Tracktor Beam

The marker dictionary, target defaults, and ArUco pose-estimation approach in
`src/drn_viz/src/landing_target_detector.cpp` were informed by ARK
Electronics' `tracktor-beam` repository at commit
`0d843dfbf61b035eb1e27b8f71e0c5674236255b`. DRN replaces its flight-control
path with the pinned PX4 ROS 2 Interface mode, stable topics, target-loss Hold,
operator preemption, and inert validation. Tracktor Beam is distributed under
the BSD-3-Clause license, copyright 2025 ARK Electronics. The upstream license
is retained in `src/drn_viz/ARK_TRACKTOR_BEAM_LICENSE`.
