# Third-party notices

DRN Stack is licensed under the MIT License except for the third-party
materials identified below. Dependencies downloaded while building the
containers remain under their respective upstream licenses.

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
