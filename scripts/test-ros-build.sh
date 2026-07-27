#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
IMAGE_NAME="${ROS_TEST_IMAGE:-drn-stack/ros-builder:test}"

docker build \
  --progress plain \
  --file "${REPO_ROOT}/docker/Dockerfile.ros" \
  --target builder \
  --tag "${IMAGE_NAME}" \
  "${REPO_ROOT}"

MSYS_NO_PATHCONV=1 docker run --rm "${IMAGE_NAME}" bash -lc '
  set -Eeo pipefail
  source /opt/ros/humble/setup.bash
  source /opt/drn_ws/install/setup.bash
  set -u
  cd /opt/drn_ws
  colcon test --merge-install --packages-select drn_viz --event-handlers console_direct+
  colcon test-result --verbose
'
