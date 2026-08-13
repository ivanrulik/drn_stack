"""Unit tests for the fail-closed hardware acceptance rules."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import time
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / 'scripts' / 'docker' / 'hardware-smoke.py'
SPEC = importlib.util.spec_from_file_location('hardware_smoke', SCRIPT_PATH)
HARDWARE_SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HARDWARE_SMOKE)


class MavlinkConstants:
    """Small constants fixture matching the MAVLink values used by validation."""

    MAV_AUTOPILOT_PX4 = 12
    MAV_MODE_FLAG_SAFETY_ARMED = 128


def packed_version(major, minor, patch, version_type=0):
    """Pack a MAVLink flight_sw_version fixture."""
    return (major << 24) | (minor << 16) | (patch << 8) | version_type


class HardwareSmokeTests(unittest.TestCase):
    """Reject wrong identity, missing configuration, and any armed sample."""

    def test_identity_accepts_pinned_px4(self):
        heartbeat = SimpleNamespace(autopilot=12, base_mode=0)
        version = SimpleNamespace(
            flight_sw_version=packed_version(1, 17, 0),
            flight_custom_version=bytes.fromhex('000000abd212eba5'),
        )
        observed = HARDWARE_SMOKE.validate_identity(
            heartbeat, version, '1.17.0', 'a5eb12d2ab', MavlinkConstants
        )
        self.assertEqual(observed['version'], '1.17.0')
        self.assertEqual(observed['git_hash'], 'a5eb12d2ab')

    def test_identity_rejects_wrong_autopilot(self):
        heartbeat = SimpleNamespace(autopilot=3, base_mode=0)
        version = SimpleNamespace(
            flight_sw_version=packed_version(1, 17, 0),
            flight_custom_version=bytes.fromhex('000000abd212eba5'),
        )
        with self.assertRaisesRegex(
            HARDWARE_SMOKE.HardwareValidationError, 'is not PX4'
        ):
            HARDWARE_SMOKE.validate_identity(
                heartbeat, version, '1.17.0', 'a5eb12d2ab', MavlinkConstants
            )

    def test_identity_rejects_wrong_firmware_and_hash(self):
        heartbeat = SimpleNamespace(autopilot=12, base_mode=0)
        wrong_version = SimpleNamespace(
            flight_sw_version=packed_version(1, 16, 0),
            flight_custom_version=bytes.fromhex('000000abd212eba5'),
        )
        with self.assertRaisesRegex(
            HARDWARE_SMOKE.HardwareValidationError, 'does not match 1.17.0'
        ):
            HARDWARE_SMOKE.validate_identity(
                heartbeat, wrong_version, '1.17.0', 'a5eb12d2ab', MavlinkConstants
            )

        wrong_hash = SimpleNamespace(
            flight_sw_version=packed_version(1, 17, 0),
            flight_custom_version=bytes.fromhex('000000efbeadde00'),
        )
        with self.assertRaisesRegex(
            HARDWARE_SMOKE.HardwareValidationError, 'git hash'
        ):
            HARDWARE_SMOKE.validate_identity(
                heartbeat, wrong_hash, '1.17.0', 'a5eb12d2ab', MavlinkConstants
            )

    def test_identity_rejects_armed_heartbeat(self):
        heartbeat = SimpleNamespace(autopilot=12, base_mode=128)
        version = SimpleNamespace(
            flight_sw_version=packed_version(1, 17, 0),
            flight_custom_version=bytes.fromhex('000000abd212eba5'),
        )
        with self.assertRaisesRegex(
            HARDWARE_SMOKE.HardwareValidationError, 'armed vehicle'
        ):
            HARDWARE_SMOKE.validate_identity(
                heartbeat, version, '1.17.0', 'a5eb12d2ab', MavlinkConstants
            )

    def test_parameters_fail_closed_when_one_is_missing(self):
        parameters = {'UXRCE_DDS_CFG': {}, 'UXRCE_DDS_PRT': {}}
        with self.assertRaisesRegex(
            HARDWARE_SMOKE.HardwareValidationError, 'UXRCE_DDS_AG_IP'
        ):
            HARDWARE_SMOKE.validate_parameters(parameters)

    def test_status_requires_distinct_disarmed_samples(self):
        with self.assertRaisesRegex(
            HARDWARE_SMOKE.HardwareValidationError, 'distinct'
        ):
            HARDWARE_SMOKE.validate_disarmed_samples([10, 10], [1, 1], 1)
        with self.assertRaisesRegex(
            HARDWARE_SMOKE.HardwareValidationError, 'remain disarmed'
        ):
            HARDWARE_SMOKE.validate_disarmed_samples([10, 11], [1, 2], 1)
        HARDWARE_SMOKE.validate_disarmed_samples([10, 11], [1, 1], 1)

    def test_multiple_or_missing_system_ids_fail_closed(self):
        self.assertEqual(HARDWARE_SMOKE.validate_single_system([1, 1]), 1)
        for system_ids in ([], [1, 2]):
            with self.assertRaisesRegex(
                HARDWARE_SMOKE.HardwareValidationError, 'expected one PX4'
            ):
                HARDWARE_SMOKE.validate_single_system(system_ids)

    def test_message_timeout_fails_closed(self):
        connection = SimpleNamespace(recv_match=lambda **kwargs: None)
        with self.assertRaisesRegex(
            HARDWARE_SMOKE.HardwareValidationError, 'timed out'
        ):
            HARDWARE_SMOKE.wait_for_message(
                connection, 'HEARTBEAT', time.monotonic() - 0.01
            )


if __name__ == '__main__':
    unittest.main()
