#!/usr/bin/env python3
"""Apply and verify allowlisted PX4 SITL failure actions."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time


PX4_BIN_DIR = Path(
    os.environ.get(
        "DRN_PX4_BIN_DIR",
        "/opt/PX4-Autopilot/build/px4_sitl_default/bin",
    )
)
PARAM = PX4_BIN_DIR / "px4-param"
FAILURE = PX4_BIN_DIR / "px4-failure"
LISTENER = PX4_BIN_DIR / "px4-listener"
DISARMED_STATE = 1
BATTERY_OFF_MAX_VOLTAGE = 14.6
BATTERY_OK_MIN_VOLTAGE = 15.5


class FailureActionError(RuntimeError):
    """Raised when a failure action is unsafe, unsupported, or unverified."""


def _run(command: list[str], timeout: float = 10.0) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise FailureActionError(f"command timed out: {' '.join(command)}") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or "no output"
        raise FailureActionError(
            f"command failed: {' '.join(command)}: {detail}"
        ) from error
    return result.stdout + result.stderr


def _topic_number(topic: str, field: str) -> float:
    output = _run([str(LISTENER), topic, "-n", "1"])
    match = re.search(rf"^\s*{re.escape(field)}:\s*(-?[0-9.]+)\s*$", output, re.MULTILINE)
    if match is None:
        raise FailureActionError(f"PX4 {topic} did not report {field}")
    return float(match.group(1))


def _require_failure_injection_enabled() -> None:
    output = _run([str(PARAM), "show", "SYS_FAILURE_EN"])
    if re.search(r"SYS_FAILURE_EN[^\n]*:\s*1\s*$", output, re.MULTILINE) is None:
        raise FailureActionError("PX4 SYS_FAILURE_EN must be enabled")


def _require_disarmed() -> None:
    arming_state = int(_topic_number("vehicle_status", "arming_state"))
    armed_time = int(_topic_number("vehicle_status", "armed_time"))
    if arming_state != DISARMED_STATE or armed_time != 0:
        raise FailureActionError(
            "PX4 must remain disarmed for the entire scenario; "
            f"arming_state={arming_state}, armed_time={armed_time}"
        )


def _wait_for_battery_state(failure_type: str, timeout: float = 10.0) -> float:
    deadline = time.monotonic() + timeout
    last_voltage = None
    while time.monotonic() < deadline:
        last_voltage = _topic_number("battery_status", "voltage_v")
        if failure_type == "off" and last_voltage <= BATTERY_OFF_MAX_VOLTAGE:
            return last_voltage
        if failure_type == "ok" and last_voltage >= BATTERY_OK_MIN_VOLTAGE:
            return last_voltage
        time.sleep(0.25)
    raise FailureActionError(
        f"battery {failure_type} effect was not observed; last voltage was {last_voltage}"
    )


def apply_failure(component: str, failure_type: str) -> None:
    """Apply one explicitly gated and measurable failure."""
    if os.environ.get("DRN_OPERATOR_ACTIONS") != "1":
        raise FailureActionError("DRN_OPERATOR_ACTIONS=1 is required")
    if (component, failure_type) != ("battery", "off"):
        raise FailureActionError(
            f"unsupported failure action: {component} {failure_type}"
        )
    _require_failure_injection_enabled()
    _require_disarmed()
    _run([str(FAILURE), component, failure_type])
    voltage = _wait_for_battery_state(failure_type)
    print(f"Verified PX4 battery failure at {voltage:.2f} V.", flush=True)


def restore_failure(component: str) -> None:
    """Restore one allowlisted failure even when the operator gate is absent."""
    if component != "battery":
        raise FailureActionError(f"unsupported failure restoration: {component}")
    _run([str(FAILURE), component, "ok"])
    voltage = _wait_for_battery_state("ok")
    _require_disarmed()
    print(f"Verified PX4 battery restoration at {voltage:.2f} V.", flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply = subparsers.add_parser("apply", help="apply an operator-gated failure")
    apply.add_argument("component")
    apply.add_argument("failure_type")

    restore = subparsers.add_parser("restore", help="restore an injected failure")
    restore.add_argument("component")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "apply":
            apply_failure(args.component, args.failure_type)
        else:
            restore_failure(args.component)
    except (FailureActionError, OSError) as error:
        print(f"drn-px4-failure: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
