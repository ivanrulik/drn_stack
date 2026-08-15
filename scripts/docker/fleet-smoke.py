#!/usr/bin/env python3
"""Validate the inert bounded-fleet ROS graph and telemetry contract."""

import os
import subprocess
import time


MIN_FLEET_SIZE = 2
MAX_FLEET_SIZE = 4


class FleetValidationError(RuntimeError):
    """A fleet namespace, telemetry, or safety contract was not satisfied."""


def fleet_size(value=None):
    """Return the validated bounded fleet size from an explicit or env value."""
    raw_value = str(
        value if value is not None else os.environ.get('DRN_FLEET_SIZE', '2')
    )
    if not raw_value.isdecimal():
        raise FleetValidationError(
            f'DRN_FLEET_SIZE must be an integer from 2 through 4; got {raw_value!r}'
        )
    size = int(raw_value)
    if not MIN_FLEET_SIZE <= size <= MAX_FLEET_SIZE:
        raise FleetValidationError(
            f'DRN_FLEET_SIZE must be an integer from 2 through 4; got {raw_value!r}'
        )
    return size


def fleet_vehicles(size=None):
    """Return the stable PX4 namespace sequence for one supported fleet."""
    resolved_size = fleet_size(size)
    return tuple(f'px4_{instance}' for instance in range(1, resolved_size + 1))


VEHICLES = fleet_vehicles()


def run_ros(command, timeout=15):
    """Run a read-only ROS CLI query and return normalized output lines."""
    result = subprocess.run(
        ['ros2', *command],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise FleetValidationError(f'ros2 {" ".join(command)} failed: {detail}')
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def validate_graph():
    """Require isolated vehicle topics and reject control or unscoped PX4 APIs."""
    nodes = set(run_ros(['node', 'list']))
    topics = set(run_ros(['topic', 'list']))
    services = set(run_ros(['service', 'list']))

    required_nodes = {'/foxglove_bridge'}
    required_topics = set()
    for vehicle in VEHICLES:
        required_nodes.update({
            f'/{vehicle}/map_origin',
            f'/{vehicle}/odometry_tf_bridge',
            f'/{vehicle}/robot_state_publisher',
        })
        required_topics.update({
            f'/{vehicle}/fmu/out/vehicle_odometry',
            f'/{vehicle}/fmu/out/vehicle_status_v1',
            f'/{vehicle}/robot_description',
        })

    missing_nodes = sorted(required_nodes - nodes)
    missing_topics = sorted(required_topics - topics)
    if missing_nodes:
        raise FleetValidationError(f'missing fleet nodes: {missing_nodes}')
    if missing_topics:
        raise FleetValidationError(f'missing fleet topics: {missing_topics}')

    unscoped = sorted(topic for topic in topics if topic.startswith('/fmu/'))
    if unscoped:
        raise FleetValidationError(f'unscoped PX4 topics are present: {unscoped}')

    graph_items = nodes | topics | services
    forbidden = sorted(
        item
        for item in graph_items
        if item == '/drn_control' or item.startswith('/drn/control/')
    )
    if forbidden:
        raise FleetValidationError(f'control endpoints are present: {forbidden}')


def collect_telemetry(timeout=60.0):
    """Require fresh odometry and continuously disarmed status from each PX4."""
    import rclpy
    from px4_msgs.msg import VehicleOdometry, VehicleStatus
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data

    class Collector(Node):
        def __init__(self):
            super().__init__('drn_fleet_smoke')
            self.status = {vehicle: [] for vehicle in VEHICLES}
            self.odometry = {vehicle: [] for vehicle in VEHICLES}
            self._fleet_subscriptions = []
            for vehicle in VEHICLES:
                self._fleet_subscriptions.append(self.create_subscription(
                    VehicleStatus,
                    f'/{vehicle}/fmu/out/vehicle_status_v1',
                    lambda message, name=vehicle: self.status[name].append(
                        (int(message.timestamp), int(message.arming_state))
                    ),
                    qos_profile_sensor_data,
                ))
                self._fleet_subscriptions.append(self.create_subscription(
                    VehicleOdometry,
                    f'/{vehicle}/fmu/out/vehicle_odometry',
                    lambda message, name=vehicle: self.odometry[name].append(
                        int(message.timestamp)
                    ),
                    qos_profile_sensor_data,
                ))

    rclpy.init(args=None)
    node = Collector()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.25)
            if all(
                len({timestamp for timestamp, _ in node.status[vehicle]}) >= 3
                and len(set(node.odometry[vehicle])) >= 3
                for vehicle in VEHICLES
            ):
                break

        for vehicle in VEHICLES:
            status = node.status[vehicle]
            odometry = node.odometry[vehicle]
            if len({timestamp for timestamp, _ in status}) < 3:
                raise FleetValidationError(
                    f'{vehicle} did not publish three distinct status samples'
                )
            if any(
                arming_state != VehicleStatus.ARMING_STATE_DISARMED
                for _, arming_state in status
            ):
                raise FleetValidationError(f'{vehicle} did not remain disarmed')
            if len(set(odometry)) < 3 or not all(
                timestamp > 0 for timestamp in odometry
            ):
                raise FleetValidationError(
                    f'{vehicle} did not publish three fresh odometry samples'
                )
    finally:
        node.destroy_node()
        rclpy.shutdown()


def main():
    """Run the complete read-only fleet acceptance check."""
    collect_telemetry()
    validate_graph()
    print(
        f'Fleet smoke passed: {", ".join(VEHICLES)} are isolated and disarmed.'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
