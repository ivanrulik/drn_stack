#!/usr/bin/env python3
"""Validate the inert x500 precision-landing perception contract."""

import math
import os
import sys
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from px4_msgs.msg import VehicleStatus
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import Bool


REQUIRED_SAMPLES = 3


class PrecisionLandingSmoke(Node):
    """Collect camera, detector, and vehicle-state samples without commanding PX4."""

    def __init__(self):
        super().__init__(
            f'drn_precision_landing_smoke_{os.getpid()}', enable_rosout=False
        )
        self.counts = {'image': 0, 'camera_info': 0, 'visible': 0}
        self.errors = {}
        self.arming_state = None
        self.target_count = 0
        self._subscriptions = [
            self.create_subscription(
                Image,
                '/drn/sensors/landing/image_raw',
                self._image,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                CameraInfo,
                '/drn/sensors/landing/camera_info',
                self._camera_info,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                Bool,
                '/drn/sensors/landing/visible',
                self._visible,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                PoseStamped,
                '/drn/sensors/landing/target_pose',
                self._target,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                VehicleStatus,
                '/fmu/out/vehicle_status_v1',
                self._vehicle_status,
                qos_profile_sensor_data,
            ),
        ]

    def _image(self, message):
        error = None
        if message.width <= 0 or message.height <= 0 or message.step <= 0:
            error = f'invalid image dimensions {message.width}x{message.height}'
        elif len(message.data) < message.height * message.step:
            error = 'truncated image data'
        if error:
            self.errors['image'] = error
            return
        self.errors.pop('image', None)
        self.counts['image'] += 1

    def _camera_info(self, message):
        error = None
        if message.width <= 0 or message.height <= 0:
            error = f'invalid calibration dimensions {message.width}x{message.height}'
        elif len(message.k) != 9 or message.k[0] <= 0 or message.k[4] <= 0:
            error = 'invalid camera intrinsic matrix'
        if error:
            self.errors['camera_info'] = error
            return
        self.errors.pop('camera_info', None)
        self.counts['camera_info'] += 1

    def _visible(self, _message):
        self.counts['visible'] += 1

    def _target(self, message):
        position = message.pose.position
        values = (position.x, position.y, position.z)
        if message.header.frame_id != 'landing_camera_optical':
            self.errors['target'] = f'frame_id={message.header.frame_id!r}'
        elif not all(math.isfinite(value) for value in values) or position.z <= 0:
            self.errors['target'] = f'invalid position={values}'
        else:
            self.errors.pop('target', None)
            self.target_count += 1

    def _vehicle_status(self, message):
        self.arming_state = message.arming_state

    def complete(self):
        return (
            all(count >= REQUIRED_SAMPLES for count in self.counts.values())
            and self.arming_state is not None
        )


def main():
    """Verify perception wiring and prove the automated check remains disarmed."""
    rclpy.init()
    node = PrecisionLandingSmoke()
    deadline = time.monotonic() + 90.0
    try:
        while time.monotonic() < deadline and not node.complete():
            rclpy.spin_once(node, timeout_sec=0.5)

        if not node.complete() or node.errors:
            print(
                'Precision-landing smoke failed: '
                f'counts={node.counts}, targets={node.target_count}, '
                f'errors={node.errors}, arming_state={node.arming_state}',
                file=sys.stderr,
            )
            return 1
        if node.arming_state != VehicleStatus.ARMING_STATE_DISARMED:
            print(
                f'PX4 is not disarmed (arming_state={node.arming_state}).',
                file=sys.stderr,
            )
            return 1

        print(
            'Precision-landing smoke passed: camera, calibration, and detector '
            f'heartbeat received; targets={node.target_count}; PX4 disarmed.'
        )
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
