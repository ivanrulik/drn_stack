#!/usr/bin/env python3
"""Fail-closed, read-only acceptance check for a PX4 UDP bench connection."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time


EXPECTED_TOPIC_TYPES = {
    '/fmu/out/vehicle_status_v1': 'px4_msgs/msg/VehicleStatus',
    '/fmu/out/vehicle_odometry': 'px4_msgs/msg/VehicleOdometry',
}
DEFAULT_PARAMETERS = (
    'UXRCE_DDS_CFG',
    'UXRCE_DDS_PRT',
    'UXRCE_DDS_AG_IP',
    'MAV_2_CONFIG',
    'MAV_2_MODE',
    'MAV_2_REMOTE_PRT',
    'MAV_2_UDP_PRT',
)


class HardwareValidationError(RuntimeError):
    """A hardware precondition or safety invariant was not satisfied."""


def decode_flight_version(encoded):
    """Decode MAVLink's packed major/minor/patch firmware version."""
    value = int(encoded)
    return f'{value >> 24}.{(value >> 16) & 0xff}.{(value >> 8) & 0xff}'


def decode_custom_version(value):
    """Decode the five git bytes retained by PX4 v1.17 AUTOPILOT_VERSION."""
    if isinstance(value, str):
        value = value.encode('latin1')
    raw = bytes(value)
    if len(raw) != 8:
        raise HardwareValidationError(
            f'flight_custom_version has {len(raw)} bytes instead of 8'
        )
    # PX4 v1.17 puts a little-endian, masked uint64 here, then overwrites the
    # first three bytes with its vendor version. Bytes 3..7 retain the first
    # five bytes of the git hash in reverse order.
    return raw[3:][::-1].hex()


def validate_identity(heartbeat, version, expected_version, expected_hash, mavlink):
    """Validate PX4 identity without invoking a shell or changing the device."""
    if heartbeat.autopilot != mavlink.MAV_AUTOPILOT_PX4:
        raise HardwareValidationError(
            f'heartbeat autopilot {heartbeat.autopilot} is not PX4'
        )
    if heartbeat.base_mode & mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
        raise HardwareValidationError('PX4 heartbeat reports an armed vehicle')

    observed_version = decode_flight_version(version.flight_sw_version)
    observed_hash = decode_custom_version(version.flight_custom_version)
    if observed_version != expected_version:
        raise HardwareValidationError(
            f'PX4 firmware {observed_version} does not match {expected_version}'
        )
    if not observed_hash.startswith(expected_hash.lower()):
        raise HardwareValidationError(
            f'PX4 git hash {observed_hash} does not match {expected_hash}'
        )
    return {'version': observed_version, 'git_hash': observed_hash}


def validate_parameters(parameters, required=DEFAULT_PARAMETERS):
    """Require the transport parameters to be readable; never set them."""
    missing = sorted(set(required) - set(parameters))
    if missing:
        raise HardwareValidationError(
            f'missing required PX4 parameters: {", ".join(missing)}'
        )


def validate_single_system(system_ids):
    """Reject ambiguous links before sending any targeted request."""
    unique_ids = sorted(set(system_ids))
    if len(unique_ids) != 1:
        raise HardwareValidationError(
            f'expected one PX4 system id, detected: {unique_ids}'
        )
    return unique_ids[0]


def validate_disarmed_samples(status_timestamps, arming_states, disarmed_value):
    """Require two fresh, distinct samples and a continuously disarmed state."""
    if len(set(status_timestamps)) < 2:
        raise HardwareValidationError('did not receive two distinct vehicle-status samples')
    if any(state != disarmed_value for state in arming_states):
        raise HardwareValidationError('vehicle status did not remain disarmed')


def run_ros(command, timeout=10):
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
        raise HardwareValidationError(
            f'ros2 {" ".join(command)} failed: {detail}'
        )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def validate_ros_graph():
    """Verify exact PX4 message types and absence of DRN control endpoints."""
    observed_types = {}
    for topic, expected_type in EXPECTED_TOPIC_TYPES.items():
        types = run_ros(['topic', 'type', topic])
        if types != [expected_type]:
            raise HardwareValidationError(
                f'{topic} type {types!r} does not match {expected_type}'
            )
        observed_types[topic] = expected_type

    nodes = run_ros(['node', 'list'])
    topics = run_ros(['topic', 'list'])
    services = run_ros(['service', 'list'])
    forbidden = sorted(
        item
        for item in (*nodes, *topics, *services)
        if item == '/drn_control' or item.startswith('/drn/control/')
    )
    if forbidden:
        raise HardwareValidationError(
            f'control endpoints are present in hardware mode: {forbidden}'
        )
    return {'topic_types': observed_types, 'control_endpoints': []}


def wait_for_message(connection, message_type, deadline, system_id=None):
    """Receive a MAVLink message of one type from an optional target system."""
    while time.monotonic() < deadline:
        message = connection.recv_match(type=message_type, blocking=True, timeout=0.5)
        if message is None:
            continue
        if system_id is None or message.get_srcSystem() == system_id:
            return message
    raise HardwareValidationError(f'timed out waiting for MAVLink {message_type}')


def collect_mavlink(port, timeout, expected_version, expected_hash, parameter_names):
    """Read PX4 identity and selected parameters over MAVLink."""
    from pymavlink import mavutil

    deadline = time.monotonic() + timeout
    connection = mavutil.mavlink_connection(
        f'udpin:0.0.0.0:{port}',
        source_system=255,
        source_component=mavutil.mavlink.MAV_COMP_ID_ONBOARD_COMPUTER,
    )
    heartbeat = wait_for_message(connection, 'HEARTBEAT', deadline)
    system_id = heartbeat.get_srcSystem()
    component_id = heartbeat.get_srcComponent()

    seen_systems = {system_id}
    discovery_deadline = min(deadline, time.monotonic() + 2.0)
    while time.monotonic() < discovery_deadline:
        candidate = connection.recv_match(type='HEARTBEAT', blocking=True, timeout=0.25)
        if candidate and candidate.autopilot == mavutil.mavlink.MAV_AUTOPILOT_PX4:
            seen_systems.add(candidate.get_srcSystem())
    validate_single_system(seen_systems)

    connection.mav.command_long_send(
        system_id,
        component_id,
        mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE,
        0,
        mavutil.mavlink.MAVLINK_MSG_ID_AUTOPILOT_VERSION,
        0, 0, 0, 0, 0, 0,
    )
    version = wait_for_message(
        connection, 'AUTOPILOT_VERSION', deadline, system_id
    )
    identity = validate_identity(
        heartbeat, version, expected_version, expected_hash, mavutil.mavlink
    )

    parameters = {}
    for name in parameter_names:
        connection.mav.param_request_read_send(
            system_id, component_id, name.encode('ascii'), -1
        )
        while time.monotonic() < deadline:
            message = wait_for_message(connection, 'PARAM_VALUE', deadline, system_id)
            parameter_id = message.param_id
            if isinstance(parameter_id, bytes):
                parameter_id = parameter_id.decode('ascii', errors='replace')
            parameter_id = parameter_id.rstrip('\x00')
            if parameter_id == name:
                parameters[name] = {
                    'value': message.param_value,
                    'type': message.param_type,
                }
                break
    validate_parameters(parameters, parameter_names)
    connection.close()
    return {
        'system_id': system_id,
        'component_id': component_id,
        **identity,
        'parameters': parameters,
    }


def collect_ros_samples(timeout):
    """Read telemetry directly with rclpy using PX4's sensor-data QoS."""
    import rclpy
    from px4_msgs.msg import VehicleOdometry, VehicleStatus
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data

    class Collector(Node):
        def __init__(self):
            super().__init__('drn_hardware_acceptance')
            self.status_timestamps = []
            self.arming_states = []
            self.odometry_timestamps = []
            self.create_subscription(
                VehicleStatus,
                '/fmu/out/vehicle_status_v1',
                self.on_status,
                qos_profile_sensor_data,
            )
            self.create_subscription(
                VehicleOdometry,
                '/fmu/out/vehicle_odometry',
                self.on_odometry,
                qos_profile_sensor_data,
            )

        def on_status(self, message):
            self.status_timestamps.append(int(message.timestamp))
            self.arming_states.append(int(message.arming_state))

        def on_odometry(self, message):
            self.odometry_timestamps.append(int(message.timestamp))

    rclpy.init(args=None)
    node = Collector()
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.25)
            if (
                len(set(node.status_timestamps)) >= 2
                and any(timestamp > 0 for timestamp in node.odometry_timestamps)
            ):
                break
        validate_disarmed_samples(
            node.status_timestamps,
            node.arming_states,
            VehicleStatus.ARMING_STATE_DISARMED,
        )
        if not any(timestamp > 0 for timestamp in node.odometry_timestamps):
            raise HardwareValidationError('did not receive PX4 vehicle odometry')
        return {
            'status_timestamps': node.status_timestamps[:10],
            'arming_states': node.arming_states[:10],
            'odometry_timestamps': node.odometry_timestamps[:10],
        }
    finally:
        node.destroy_node()
        rclpy.shutdown()


def write_report(report, report_directory):
    """Write an immutable timestamped acceptance report."""
    directory = Path(report_directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    path = directory / f'hardware-udp-{stamp}.json'
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return path


def parse_args(argv):
    """Parse command-line options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout', type=float, default=30.0)
    parser.add_argument('--port', type=int, default=int(os.getenv('MAVLINK_PORT', '14580')))
    parser.add_argument('--report-directory', default='/artifacts/hardware')
    return parser.parse_args(argv)


def main(argv=None):
    """Run every fail-closed check and always emit a durable report."""
    args = parse_args(argv)
    expected_version = os.getenv('DRN_EXPECTED_PX4_VERSION', '1.17.0')
    expected_hash = os.getenv('DRN_EXPECTED_PX4_GIT_HASH', 'a5eb12d2ab')
    parameters = tuple(
        name.strip()
        for name in os.getenv(
            'DRN_HARDWARE_PARAMETERS', ','.join(DEFAULT_PARAMETERS)
        ).split(',')
        if name.strip()
    )
    report = {
        'schema': 'drn.hardware-acceptance/v1',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'connection': 'hardware-udp',
        'software': {
            'drn_revision': os.getenv('DRN_GIT_REVISION', 'unknown'),
            'drn_worktree_dirty': os.getenv('DRN_GIT_DIRTY', 'unknown'),
            'image_id': os.getenv('DRN_IMAGE_ID', 'unknown'),
            'expected_px4_version': expected_version,
            'expected_px4_git_hash': expected_hash,
        },
        'verdict': 'failed',
    }
    exit_code = 1
    try:
        report['mavlink'] = collect_mavlink(
            args.port, args.timeout, expected_version, expected_hash, parameters
        )
        report['ros_graph'] = validate_ros_graph()
        report['telemetry'] = collect_ros_samples(args.timeout)
        report['verdict'] = 'passed'
        exit_code = 0
    except (HardwareValidationError, OSError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    except Exception as error:  # Keep a report for unexpected bench failures.
        report['error'] = f'{type(error).__name__}: {error}'

    path = write_report(report, args.report_directory)
    print(f'Hardware acceptance report: {path}')
    if exit_code:
        print(f'Hardware acceptance failed: {report["error"]}', file=sys.stderr)
    else:
        print('Hardware UDP acceptance passed; PX4 remained disarmed.')
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
