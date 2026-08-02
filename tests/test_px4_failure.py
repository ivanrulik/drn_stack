"""Focused tests for fail-closed PX4 SITL failure actions."""

import importlib.util
import os
from pathlib import Path
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "docker" / "px4-failure.py"
SPEC = importlib.util.spec_from_file_location("drn_px4_failure", MODULE_PATH)
PX4_FAILURE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PX4_FAILURE)


class Px4FailureTests(unittest.TestCase):
    """Validate the operator gate, allowlist, and measurable restoration."""

    def test_apply_requires_explicit_operator_gate(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(
                PX4_FAILURE.FailureActionError, "DRN_OPERATOR_ACTIONS=1"
            ):
                PX4_FAILURE.apply_failure("battery", "off")

    def test_apply_rejects_unallowlisted_failure(self):
        with mock.patch.dict(os.environ, {"DRN_OPERATOR_ACTIONS": "1"}, clear=True):
            with self.assertRaisesRegex(
                PX4_FAILURE.FailureActionError, "unsupported failure action"
            ):
                PX4_FAILURE.apply_failure("gps", "off")

    def test_apply_requires_disarmed_vehicle_and_verifies_effect(self):
        with (
            mock.patch.dict(
                os.environ, {"DRN_OPERATOR_ACTIONS": "1"}, clear=True
            ),
            mock.patch.object(
                PX4_FAILURE,
                "_run",
                side_effect=[
                    "x SYS_FAILURE_EN [981,1559] : 1\n",
                    "arming_state: 1\n",
                    "armed_time: 0\n",
                    "failure accepted\n",
                ],
            ) as run,
            mock.patch.object(
                PX4_FAILURE, "_wait_for_battery_state", return_value=14.4
            ) as wait,
        ):
            PX4_FAILURE.apply_failure("battery", "off")

        self.assertEqual("off", wait.call_args.args[0])
        self.assertIn("px4-failure", str(run.call_args_list[-1]))

    def test_apply_refuses_armed_vehicle(self):
        with (
            mock.patch.dict(
                os.environ, {"DRN_OPERATOR_ACTIONS": "1"}, clear=True
            ),
            mock.patch.object(
                PX4_FAILURE,
                "_run",
                side_effect=[
                    "x SYS_FAILURE_EN [981,1559] : 1\n",
                    "arming_state: 2\n",
                    "armed_time: 1000\n",
                ],
            ),
        ):
            with self.assertRaisesRegex(
                PX4_FAILURE.FailureActionError, "must remain disarmed"
            ):
                PX4_FAILURE.apply_failure("battery", "off")

    def test_restore_is_always_available_and_verified(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(PX4_FAILURE, "_run", return_value="failure restored\n"),
            mock.patch.object(
                PX4_FAILURE, "_wait_for_battery_state", return_value=16.2
            ) as wait,
            mock.patch.object(PX4_FAILURE, "_require_disarmed") as disarmed,
        ):
            PX4_FAILURE.restore_failure("battery")

        self.assertEqual("ok", wait.call_args.args[0])
        disarmed.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
