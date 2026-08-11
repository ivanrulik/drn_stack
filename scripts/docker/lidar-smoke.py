#!/usr/bin/env python3
"""Validate the inert x500-lidar ROS LaserScan contract."""

import math
import os
import sys
import time

from px4_msgs.msg import VehicleStatus
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import LaserScan
from visualization_msgs.msg import Marker, MarkerArray


EXPECTED_FRAME = 'lidar_link'
EXPECTED_SAMPLES = 1080
REQUIRED_MESSAGES = 3
EXPECTED_WALLS = {
    0: ((5.0, 0.0, 7.5), (1.0, 20.0, 15.0)),
    1: ((-3.0, 5.0, 7.5), (10.0, 1.0, 15.0)),
    2: ((13.0, -10.0, 7.5), (17.0, 1.0, 15.0)),
    3: ((12.0, 0.0, 7.5), (1.0, 20.0, 15.0)),
}


class LidarSmoke(Node):
    """Collect and validate bounded 2D LiDAR samples."""

    def __init__(self):
        super().__init__(f'drn_lidar_smoke_{os.getpid()}', enable_rosout=False)
        self.samples = 0
        self.timestamps = set()
        self.errors = []
        self.arming_state = None
        self.walls_valid = False
        self._subscriptions = [
            self.create_subscription(
                LaserScan,
                '/drn/sensors/lidar/scan',
                self._scan,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                VehicleStatus,
                '/fmu/out/vehicle_status_v1',
                self._vehicle_status,
                qos_profile_sensor_data,
            ),
            self.create_subscription(
                MarkerArray,
                '/drn/viz/lidar/walls',
                self._walls,
                10,
            ),
        ]

    def _scan(self, message):
        metadata = (
            message.angle_min,
            message.angle_max,
            message.angle_increment,
            message.time_increment,
            message.scan_time,
            message.range_min,
            message.range_max,
        )
        error = None
        if message.header.frame_id != EXPECTED_FRAME:
            error = f'frame_id={message.header.frame_id!r}'
        elif not all(math.isfinite(value) for value in metadata):
            error = 'scan metadata contains a non-finite value'
        elif len(message.ranges) != EXPECTED_SAMPLES:
            error = f'expected {EXPECTED_SAMPLES} ranges, got {len(message.ranges)}'
        elif message.intensities and len(message.intensities) != EXPECTED_SAMPLES:
            error = (
                f'expected zero or {EXPECTED_SAMPLES} intensities, '
                f'got {len(message.intensities)}'
            )
        elif not math.isclose(message.angle_min, -2.356195, abs_tol=1e-5):
            error = f'unexpected angle_min={message.angle_min}'
        elif not math.isclose(message.angle_max, 2.356195, abs_tol=1e-5):
            error = f'unexpected angle_max={message.angle_max}'
        elif message.angle_increment <= 0:
            error = f'invalid angle_increment={message.angle_increment}'
        elif not math.isclose(message.range_min, 0.1, abs_tol=1e-5):
            error = f'unexpected range_min={message.range_min}'
        elif not math.isclose(message.range_max, 30.0, abs_tol=1e-5):
            error = f'unexpected range_max={message.range_max}'
        else:
            finite_ranges = [
                value for value in message.ranges if math.isfinite(value)
            ]
            invalid_ranges = [
                value
                for value in message.ranges
                if not (
                    math.isinf(value) and value > 0
                    or math.isfinite(value)
                    and message.range_min <= value <= message.range_max
                )
            ]
            if invalid_ranges:
                error = f'invalid range sample={invalid_ranges[0]}'
            elif not finite_ranges:
                error = 'scan contains no finite obstacle returns'

        if error:
            self.errors.append(error)
            return

        self.timestamps.add((message.header.stamp.sec, message.header.stamp.nanosec))
        self.samples += 1

    def _vehicle_status(self, message):
        self.arming_state = message.arming_state

    def _walls(self, message):
        walls = {
            marker.id: marker
            for marker in message.markers
            if marker.ns == 'lidar_world_walls'
            and marker.action == Marker.ADD
        }
        if set(walls) != set(EXPECTED_WALLS):
            self.errors.append(f'unexpected wall marker IDs={sorted(walls)}')
            return

        for marker_id, (position, scale) in EXPECTED_WALLS.items():
            marker = walls[marker_id]
            actual_position = (
                marker.pose.position.x,
                marker.pose.position.y,
                marker.pose.position.z,
            )
            actual_scale = (marker.scale.x, marker.scale.y, marker.scale.z)
            if marker.header.frame_id != 'map':
                self.errors.append(
                    f'wall {marker_id} frame={marker.header.frame_id!r}'
                )
                return
            if marker.type != Marker.CUBE:
                self.errors.append(f'wall {marker_id} type={marker.type}')
                return
            if not all(
                math.isclose(actual, expected, abs_tol=1e-6)
                for actual, expected in zip(actual_position, position)
            ):
                self.errors.append(
                    f'wall {marker_id} position={actual_position}'
                )
                return
            if not all(
                math.isclose(actual, expected, abs_tol=1e-6)
                for actual, expected in zip(actual_scale, scale)
            ):
                self.errors.append(f'wall {marker_id} scale={actual_scale}')
                return
            if marker.color.a <= 0:
                self.errors.append(f'wall {marker_id} is transparent')
                return

        self.walls_valid = True

    def complete(self):
        return (
            self.samples >= REQUIRED_MESSAGES
            and len(self.timestamps) >= REQUIRED_MESSAGES
            and self.arming_state is not None
            and self.walls_valid
        )


def main():
    """Wait for valid scans and verify PX4 remains disarmed."""
    rclpy.init()
    node = LidarSmoke()
    deadline = time.monotonic() + 90.0
    try:
        while time.monotonic() < deadline and not node.complete():
            rclpy.spin_once(node, timeout_sec=0.5)

        if not node.complete():
            print(
                'x500-lidar smoke timed out: '
                f'samples={node.samples}, timestamps={len(node.timestamps)}, '
                f'walls_valid={node.walls_valid}, errors={node.errors[-3:]}, '
                f'arming_state={node.arming_state}',
                file=sys.stderr,
            )
            return 1
        if node.errors:
            print(f'x500-lidar validation failed: {node.errors[-3:]}', file=sys.stderr)
            return 1
        if node.arming_state != VehicleStatus.ARMING_STATE_DISARMED:
            print(
                f'PX4 is not disarmed (arming_state={node.arming_state}).',
                file=sys.stderr,
            )
            return 1

        print(
            'x500-lidar smoke passed: '
            f'{REQUIRED_MESSAGES} distinct {EXPECTED_SAMPLES}-ray scans with '
            f'finite obstacle returns and {len(EXPECTED_WALLS)} wall markers; '
            'PX4 disarmed.'
        )
        return 0
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    raise SystemExit(main())
