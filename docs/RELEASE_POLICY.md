# Release policy

DRN Stack uses Semantic Versioning for repository releases and keeps its ROS
packages on the same version.

## Version scheme

Versions use `MAJOR.MINOR.PATCH`:

- `PATCH` contains backward-compatible fixes and documentation changes.
- Before 1.0, `MINOR` may add features or make documented breaking changes.
- At and after 1.0, `MINOR` adds backward-compatible functionality and `MAJOR`
  contains incompatible changes.

The project is currently pre-1.0. Public APIs include documented scripts and
arguments, Compose configuration, ROS topics and services, package-installed
headers, launch arguments, environment variables, saved layout control
bindings, and declared safety behavior.

## Repository and package versions

- Git release tags use `vMAJOR.MINOR.PATCH`.
- `drn_control` and `drn_viz` use the same version as the repository release.
- Package versions are updated together in one release-preparation change.
- A version change alone does not create a release; the Git tag and release
  notes identify the published version.
- No compatibility is promised for an untagged commit beyond its documented
  baseline.

## Upstream dependency pins

The exact supported combination is defined in
[`docs/COMPATIBILITY.md`](COMPATIBILITY.md) and `compose.yaml`.

- Git dependencies remain pinned to immutable commits.
- Pin changes are deliberate compatibility changes and require the full
  baseline validation gate.
- A release note must identify every changed upstream pin and any migration or
  safety impact.
- DRN Stack does not claim support for arbitrary combinations of PX4,
  `px4_msgs`, the ROS 2 Interface Library, ROS 2, or Gazebo.

## Release gate

Before creating a tag:

1. Confirm a clean branch based on current `main`.
2. Update both ROS package versions and relevant release documentation.
3. Run repository lint and ROS build/ament tests.
4. Run the full disarmed Docker integration smoke test.
5. Record any required operator-in-the-loop checks that remain pending.
6. Review third-party notices when vendored assets or dependencies changed.
7. Publish release notes with the supported compatibility baseline.

Release tags, GitHub releases, and backports are explicit maintainer actions.
Merging a pull request does not create any of them automatically.

## Support window

Until 1.0, fixes target `main` and the latest tagged release on a best-effort
basis. Older pre-1.0 versions do not receive guaranteed backports. A longer
support window may be defined when the public API and hardware profile mature.
