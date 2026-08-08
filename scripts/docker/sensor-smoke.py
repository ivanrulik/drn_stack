#!/usr/bin/env python3
"""Validate the inert x500-depth ROS sensor contract."""

import os
import sys
import time

import rclpy
from px4_msgs.msg import VehicleStatus
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image


EXPECTED_FRAME = 'camera_link'
REQUIRED_SAMPLES = 3


class SensorSmoke(Node):
    """Collect and validate a bounded set of depth-profile samples."""

    def __init__(self):
        super().__init__(f'drn_sensor_smoke_{os.getpid()}', enable_rosout=False)
        self.counts = {
            'color': 0,
            'color_info': 0,
            'depth': 0,
            'depth_info': 0,
        }
        self.errors = {}
        self.image_dimensions = {}
        self.info_dimensions = {}
        self.arming_state = None
        self._subscriptions = [
            self.create_subscription(
                Image,
                '/drn/sensors/front/color/image_raw',
                lambda message: self._image('color', message),
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                Image,
                '/drn/sensors/front/depth/image_raw',
                lambda message: self._image('depth', message),
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                CameraInfo,
                '/drn/sensors/front/color/camera_info',
                lambda message: self._camera_info('color_info', message),
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                CameraInfo,
                '/drn/sensors/front/depth/camera_info',
                lambda message: self._camera_info('depth_info', message),
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                VehicleStatus,
                '/fmu/out/vehicle_status_v1',
                self._vehicle_status,
                qos_profile_sensor_data,
            ),
        ]

    def _image(self, name, message):
        error = None
        if message.header.frame_id != EXPECTED_FRAME:
            error = f'frame_id={message.header.frame_id!r}'
        elif message.width <= 0 or message.height <= 0 or message.step <= 0:
            error = (
                f'invalid dimensions {message.width}x{message.height} '
                f'step={message.step}'
            )
        elif len(message.data) < message.height * message.step:
            error = (
                f'truncated data: {len(message.data)} bytes for '
                f'{message.height} rows at step {message.step}'
            )
        elif name == 'depth' and message.encoding != '32FC1':
            error = f'unexpected depth encoding {message.encoding!r}'
        elif name == 'color' and message.encoding not in ('rgb8', 'bgr8', 'rgba8', 'bgra8'):
            error = f'unexpected color encoding {message.encoding!r}'

        if error:
            self.errors[name] = error
            return
        self.errors.pop(name, None)
        self.image_dimensions[name] = (message.width, message.height)
        self.counts[name] += 1

    def _camera_info(self, name, message):
        error = None
        if message.header.frame_id != EXPECTED_FRAME:
            error = f'frame_id={message.header.frame_id!r}'
        elif message.width <= 0 or message.height <= 0:
            error = f'invalid dimensions {message.width}x{message.height}'
        elif len(message.k) != 9 or message.k[0] <= 0 or message.k[4] <= 0:
            error = 'invalid camera intrinsic matrix'

        if error:
            self.errors[name] = error
            return
        self.errors.pop(name, None)
        self.info_dimensions[name.removesuffix('_info')] = (
            message.width,
            message.height,
        )
        self.counts[name] += 1

    def _vehicle_status(self, message):
        self.arming_state = message.arming_state

    def complete(self):
        return (
            all(count >= REQUIRED_SAMPLES for count in self.counts.values())
            and self.arming_state is not None
        )


def main():
    """Wait for valid sensor samples and verify PX4 remains disarmed."""
    rclpy.init()
    node = SensorSmoke()
    deadline = time.monotonic() + 90.0
    try:
        while time.monotonic() < deadline and not node.complete():
            rclpy.spin_once(node, timeout_sec=0.5)

        if not node.complete():
            print(
                'x500-depth sensor smoke timed out: '
                f'counts={node.counts}, errors={node.errors}, '
                f'arming_state={node.arming_state}',
                file=sys.stderr,
            )
            return 1
        if node.errors:
            print(f'x500-depth sensor validation failed: {node.errors}', file=sys.stderr)
            return 1
        if node.image_dimensions != node.info_dimensions:
            print(
                'Image and camera-info dimensions differ: '
                f'images={node.image_dimensions}, info={node.info_dimensions}',
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
            'x500-depth sensor smoke passed: '
            f'{REQUIRED_SAMPLES} color/depth images and calibrations; PX4 disarmed.'
        )
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
