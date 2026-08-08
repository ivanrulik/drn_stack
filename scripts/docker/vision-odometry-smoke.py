#!/usr/bin/env python3
"""Validate the inert simulated vision-odometry ROS contract."""

import math
import os
import sys
import time

from nav_msgs.msg import Odometry
from px4_msgs.msg import VehicleStatus
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data


REQUIRED_SAMPLES = 3


class VisionOdometrySmoke(Node):
    """Collect and validate bounded vision-odometry samples."""

    def __init__(self):
        super().__init__(f'drn_vision_odometry_smoke_{os.getpid()}', enable_rosout=False)
        self.samples = 0
        self.timestamps = set()
        self.errors = []
        self.arming_state = None
        self._subscriptions = [
            self.create_subscription(
                Odometry,
                '/drn/sensors/vision/odometry',
                self._odometry,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                VehicleStatus,
                '/fmu/out/vehicle_status_v1',
                self._vehicle_status,
                qos_profile_sensor_data,
            ),
        ]

    def _odometry(self, message):
        values = (
            message.pose.pose.position.x,
            message.pose.pose.position.y,
            message.pose.pose.position.z,
            message.pose.pose.orientation.x,
            message.pose.pose.orientation.y,
            message.pose.pose.orientation.z,
            message.pose.pose.orientation.w,
            message.twist.twist.linear.x,
            message.twist.twist.linear.y,
            message.twist.twist.linear.z,
            message.twist.twist.angular.x,
            message.twist.twist.angular.y,
            message.twist.twist.angular.z,
            *message.pose.covariance,
            *message.twist.covariance,
        )
        error = None
        if message.header.frame_id != 'map':
            error = f'frame_id={message.header.frame_id!r}'
        elif message.child_frame_id != 'base_link':
            error = f'child_frame_id={message.child_frame_id!r}'
        elif not all(math.isfinite(value) for value in values):
            error = 'pose, twist, or covariance contains a non-finite value'
        else:
            quaternion = message.pose.pose.orientation
            norm = math.sqrt(
                quaternion.x ** 2
                + quaternion.y ** 2
                + quaternion.z ** 2
                + quaternion.w ** 2
            )
            if not 0.99 <= norm <= 1.01:
                error = f'orientation quaternion norm is {norm}'

        if error:
            self.errors.append(error)
            return

        self.timestamps.add((message.header.stamp.sec, message.header.stamp.nanosec))
        self.samples += 1

    def _vehicle_status(self, message):
        self.arming_state = message.arming_state

    def complete(self):
        return (
            self.samples >= REQUIRED_SAMPLES
            and len(self.timestamps) >= REQUIRED_SAMPLES
            and self.arming_state is not None
        )


def main():
    """Wait for valid samples and verify PX4 remains disarmed."""
    rclpy.init()
    node = VisionOdometrySmoke()
    deadline = time.monotonic() + 90.0
    try:
        while time.monotonic() < deadline and not node.complete():
            rclpy.spin_once(node, timeout_sec=0.5)

        if not node.complete():
            print(
                'vision-odometry smoke timed out: '
                f'samples={node.samples}, timestamps={len(node.timestamps)}, '
                f'errors={node.errors[-3:]}, arming_state={node.arming_state}',
                file=sys.stderr,
            )
            return 1
        if node.errors:
            print(
                f'vision-odometry validation failed: {node.errors[-3:]}',
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
            'Vision-odometry smoke passed: '
            f'{REQUIRED_SAMPLES} finite ENU/FLU samples; PX4 disarmed.'
        )
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
