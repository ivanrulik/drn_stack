# Support

DRN Stack is a community-maintained development environment. Support is
provided on a best-effort basis.

## Before opening an issue

1. Review the [README](README.md) and
   [compatibility policy](docs/COMPATIBILITY.md).
2. Run the status command:

   ```powershell
   .\scripts\status.ps1
   ```

3. Capture the relevant bounded logs:

   ```powershell
   .\scripts\logs.ps1
   ```

4. Search the
   [GitHub issue tracker](https://github.com/ivanrulik/drn_stack/issues) for
   the exact error.

When opening an issue, include the host operating system, Docker version,
current Git revision, command used, exact error, and whether the problem is
reproducible from a clean DRN Stack start. Remove credentials and personal
information from all logs.

## Where to ask

Use the DRN Stack issue tracker for:

- lifecycle scripts and Compose behavior;
- the pinned ROS workspace integration;
- `drn_control` or `drn_viz`;
- the saved Foxglove layout;
- DRN-specific documentation and validation.

Use the relevant upstream project for behavior outside DRN Stack:

- [PX4 support](https://docs.px4.io/main/en/contribute/support.html)
- [ROS 2 support](https://docs.ros.org/en/humble/Contact.html)
- [Gazebo community](https://gazebosim.org/community/)
- [Foxglove support](https://docs.foxglove.dev/docs/help)

For a suspected vulnerability, do not open a public support issue. Follow
[SECURITY.md](SECURITY.md).

DRN Stack does not provide emergency, operational-flight, regulatory, or
airworthiness support. Keep testing in SITL unless an appropriate hardware
safety process is in place.
