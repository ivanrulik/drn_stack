#!/usr/bin/env python3
"""Validate and run inert DRN project scenarios."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from xml.etree import ElementTree

import yaml


SCHEMA_VERSION = 1
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
ROS_PACKAGE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ROS_NAME_PATTERN = re.compile(r"^/[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*$")
LAUNCH_ARGUMENT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
IMAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9_.-]+$")
PROJECT_DIRECTORY_EXPRESSION = (
    "${DRN_PROJECT_DIR:?Set DRN_PROJECT_DIR to the absolute project directory}"
)
MANIFEST_KEYS = {
    "schema_version",
    "name",
    "simulation",
    "launch",
    "health",
    "scenarios",
}
SCENARIO_KEYS = {
    "schema_version",
    "name",
    "timeout_seconds",
    "setup",
    "actions",
    "assertions",
    "cleanup",
}


class ConfigurationError(ValueError):
    """Raised when a project or scenario violates the extension contract."""


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be a mapping")
    return value


def _require_exact_keys(
    value: dict[str, Any], required: set[str], label: str
) -> None:
    missing = sorted(required - value.keys())
    unknown = sorted(value.keys() - required)
    if missing:
        raise ConfigurationError(f"{label} is missing keys: {', '.join(missing)}")
    if unknown:
        raise ConfigurationError(f"{label} has unknown keys: {', '.join(unknown)}")


def _require_string(value: Any, label: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ConfigurationError(f"{label} has an invalid value: {value!r}")
    return value


def _require_string_list(
    value: Any, label: str, pattern: re.Pattern[str]
) -> list[str]:
    if not isinstance(value, list):
        raise ConfigurationError(f"{label} must be a list")
    result = []
    for index, item in enumerate(value):
        result.append(_require_string(item, f"{label}[{index}]", pattern))
    if len(result) != len(set(result)):
        raise ConfigurationError(f"{label} must not contain duplicates")
    return result


def _load_yaml(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ConfigurationError(f"{label} was not found: {path}")
    try:
        with path.open(encoding="utf-8") as stream:
            value = yaml.safe_load(stream)
    except yaml.YAMLError as error:
        raise ConfigurationError(f"{label} is not valid YAML: {error}") from error
    return _require_mapping(value, label)


def load_manifest(path: Path) -> dict[str, Any]:
    manifest = _load_yaml(path, "project manifest")
    _require_exact_keys(manifest, MANIFEST_KEYS, "project manifest")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ConfigurationError(
            f"project manifest schema_version must be {SCHEMA_VERSION}"
        )

    _require_string(manifest["name"], "project manifest name", SLUG_PATTERN)

    simulation = _require_mapping(manifest["simulation"], "simulation")
    _require_exact_keys(simulation, {"vehicle", "world"}, "simulation")
    _require_string(simulation["vehicle"], "simulation.vehicle", TOKEN_PATTERN)
    _require_string(simulation["world"], "simulation.world", TOKEN_PATTERN)

    launch = _require_mapping(manifest["launch"], "launch")
    _require_exact_keys(launch, {"package", "file", "arguments"}, "launch")
    _require_string(launch["package"], "launch.package", ROS_PACKAGE_PATTERN)
    _require_string(launch["file"], "launch.file", TOKEN_PATTERN)
    arguments = _require_mapping(launch["arguments"], "launch.arguments")
    for key, value in arguments.items():
        _require_string(key, "launch argument name", LAUNCH_ARGUMENT_PATTERN)
        if not isinstance(value, (str, int, float, bool)) or isinstance(value, bytes):
            raise ConfigurationError(
                f"launch argument {key!r} must be a string, number, or boolean"
            )

    health = _require_mapping(manifest["health"], "health")
    _require_exact_keys(health, {"nodes", "topics", "services"}, "health")
    for category in ("nodes", "topics", "services"):
        _require_string_list(health[category], f"health.{category}", ROS_NAME_PATTERN)

    scenarios = _require_string_list(
        manifest["scenarios"], "scenarios", SLUG_PATTERN
    )
    if not scenarios:
        raise ConfigurationError("scenarios must contain at least one scenario")
    return manifest


def load_scenario(path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    scenario = _load_yaml(path, "scenario")
    _require_exact_keys(scenario, SCENARIO_KEYS, "scenario")
    if scenario["schema_version"] != SCHEMA_VERSION:
        raise ConfigurationError(f"scenario schema_version must be {SCHEMA_VERSION}")

    name = _require_string(scenario["name"], "scenario name", SLUG_PATTERN)
    if name not in manifest["scenarios"]:
        raise ConfigurationError(f"scenario {name!r} is not declared by the project")
    if path.stem != name:
        raise ConfigurationError(
            f"scenario filename {path.name!r} must match its name {name!r}"
        )

    timeout_seconds = scenario["timeout_seconds"]
    if (
        not isinstance(timeout_seconds, int)
        or isinstance(timeout_seconds, bool)
        or not 1 <= timeout_seconds <= 600
    ):
        raise ConfigurationError("timeout_seconds must be an integer from 1 to 600")

    setup = scenario["setup"]
    if setup != [{"type": "core-smoke"}]:
        raise ConfigurationError(
            "setup must contain exactly one inert core-smoke action"
        )

    actions = scenario["actions"]
    if actions != []:
        raise ConfigurationError(
            "schema version 1 is inert; actions must be an empty list"
        )

    assertions = scenario["assertions"]
    if not isinstance(assertions, list) or not assertions:
        raise ConfigurationError("assertions must be a non-empty list")
    for index, assertion_value in enumerate(assertions):
        assertion = _require_mapping(assertion_value, f"assertions[{index}]")
        assertion_type = assertion.get("type")
        if assertion_type == "project-health":
            _require_exact_keys(assertion, {"type"}, f"assertions[{index}]")
        elif assertion_type == "topic-message":
            _require_exact_keys(
                assertion, {"type", "name"}, f"assertions[{index}]"
            )
            _require_string(
                assertion["name"], f"assertions[{index}].name", ROS_NAME_PATTERN
            )
            if assertion["name"] not in manifest["health"]["topics"]:
                raise ConfigurationError(
                    f"assertions[{index}].name must be declared in health.topics"
                )
        else:
            raise ConfigurationError(
                f"assertions[{index}].type is not supported: {assertion_type!r}"
            )

    if scenario["cleanup"] != [{"type": "stop-stack"}]:
        raise ConfigurationError(
            "cleanup must contain exactly one stop-stack action"
        )
    return scenario


def _validate_project_packages(project_root: Path, manifest: dict[str, Any]) -> None:
    source_root = project_root / "ros_ws" / "src"
    package_paths = sorted(source_root.glob("**/package.xml"))
    if not package_paths:
        raise ConfigurationError("project ros_ws/src must contain at least one ROS package")

    package_names = []
    for path in package_paths:
        try:
            package_name = ElementTree.parse(path).getroot().findtext("name")
        except ElementTree.ParseError as error:
            raise ConfigurationError(f"invalid ROS package metadata: {path}") from error
        if not package_name or not ROS_PACKAGE_PATTERN.fullmatch(package_name):
            raise ConfigurationError(f"invalid ROS package name in {path}: {package_name!r}")
        package_names.append(package_name)

    if len(package_names) != len(set(package_names)):
        raise ConfigurationError("project ROS package names must be unique")

    underlay_index = Path("/opt/drn_ws/install/share/ament_index/resource_index/packages")
    underlay_names = {path.name for path in underlay_index.glob("*")}
    underlay_names.update({"drn_control", "drn_viz", "px4_msgs", "px4_ros_com"})
    duplicates = sorted(set(package_names) & underlay_names)
    if duplicates:
        raise ConfigurationError(
            "project packages must extend, not override, the DRN underlay: "
            + ", ".join(duplicates)
        )
    if manifest["launch"]["package"] not in package_names:
        raise ConfigurationError("launch.package must name a package in project ros_ws/src")


def _validate_compose_override(project_root: Path, manifest: dict[str, Any]) -> None:
    override = _load_yaml(project_root / "compose.override.yaml", "Compose override")
    _require_exact_keys(override, {"services"}, "Compose override")
    services = _require_mapping(override["services"], "Compose override services")
    _require_exact_keys(services, {"ros-viz"}, "Compose override services")
    ros_viz = _require_mapping(services["ros-viz"], "Compose override ros-viz")
    _require_exact_keys(
        ros_viz,
        {"image", "build", "environment", "volumes"},
        "Compose override ros-viz",
    )

    image = _require_string(ros_viz["image"], "Compose override image", IMAGE_PATTERN)
    expected_image = f"drn-stack/{manifest['name']}:humble"
    if image != expected_image:
        raise ConfigurationError(f"Compose override image must be {expected_image}")

    build = _require_mapping(ros_viz["build"], "Compose override build")
    _require_exact_keys(build, {"context", "dockerfile"}, "Compose override build")
    if build["context"] != PROJECT_DIRECTORY_EXPRESSION:
        raise ConfigurationError("Compose build context must use DRN_PROJECT_DIR")
    if build["dockerfile"] != "Dockerfile":
        raise ConfigurationError("Compose build dockerfile must be Dockerfile")

    environment = _require_mapping(
        ros_viz["environment"], "Compose override environment"
    )
    if environment != {"DRN_PROJECT_MANIFEST": "/opt/drn_project/project.yaml"}:
        raise ConfigurationError(
            "Compose override environment may only set DRN_PROJECT_MANIFEST"
        )

    expected_volume = {
        "type": "bind",
        "source": PROJECT_DIRECTORY_EXPRESSION,
        "target": "/opt/drn_project",
        "read_only": True,
    }
    if ros_viz["volumes"] != [expected_volume]:
        raise ConfigurationError(
            "Compose override must mount DRN_PROJECT_DIR read-only at /opt/drn_project"
        )


def validate_contract(manifest_path: Path, scenario_path: Path) -> tuple[dict, dict]:
    manifest_path = manifest_path.resolve()
    scenario_path = scenario_path.resolve()
    manifest = load_manifest(manifest_path)
    _validate_compose_override(manifest_path.parent, manifest)
    _validate_project_packages(manifest_path.parent, manifest)
    expected_scenario_dir = (manifest_path.parent / "scenarios").resolve()
    if scenario_path.parent != expected_scenario_dir:
        raise ConfigurationError("scenario must be inside the project's scenarios directory")
    scenario = load_scenario(scenario_path, manifest)
    return manifest, scenario


def launch_command(manifest: dict[str, Any]) -> list[str]:
    launch = manifest["launch"]
    command = ["ros2", "launch", launch["package"], launch["file"]]
    for key in sorted(launch["arguments"]):
        value = launch["arguments"][key]
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        command.append(f"{key}:={rendered}")
    return command


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("scenario timed out")
    return remaining


def _run(command: list[str], deadline: float) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=_remaining(deadline),
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"command timed out: {' '.join(command)}") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or "no output"
        raise RuntimeError(f"command failed: {' '.join(command)}: {detail}") from error
    return result.stdout


def _wait_for_project_health(manifest: dict[str, Any], deadline: float) -> None:
    commands = {
        "nodes": ["ros2", "node", "list"],
        "topics": ["ros2", "topic", "list"],
        "services": ["ros2", "service", "list"],
    }
    while True:
        missing = []
        for category, command in commands.items():
            actual = set(_run(command, deadline).splitlines())
            missing.extend(
                f"{category[:-1]} {name}"
                for name in manifest["health"][category]
                if name not in actual
            )
        if not missing:
            return
        if _remaining(deadline) <= 1:
            raise TimeoutError("missing project health signals: " + ", ".join(missing))
        time.sleep(1)


def run_scenario(manifest: dict[str, Any], scenario: dict[str, Any]) -> None:
    deadline = time.monotonic() + scenario["timeout_seconds"]
    _run(["/usr/local/bin/drn-smoke-test", "full"], deadline)
    for assertion in scenario["assertions"]:
        if assertion["type"] == "project-health":
            _wait_for_project_health(manifest, deadline)
        elif assertion["type"] == "topic-message":
            _run(
                ["ros2", "topic", "echo", "--once", assertion["name"]], deadline
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="validate a project and scenario")
    validate.add_argument("manifest", type=Path)
    validate.add_argument("scenario", type=Path)

    get_value = subparsers.add_parser("get", help="read a validated manifest value")
    get_value.add_argument("manifest", type=Path)
    get_value.add_argument("field", choices=("name", "vehicle", "world"))

    launch = subparsers.add_parser("launch", help="launch the project ROS entrypoint")
    launch.add_argument("manifest", type=Path)

    run = subparsers.add_parser("run", help="run an inert scenario")
    run.add_argument("manifest", type=Path)
    run.add_argument("scenario", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            manifest, scenario = validate_contract(args.manifest, args.scenario)
            print(f"Validated project {manifest['name']} scenario {scenario['name']}.")
        elif args.command == "get":
            manifest = load_manifest(args.manifest.resolve())
            values = {
                "name": manifest["name"],
                "vehicle": manifest["simulation"]["vehicle"],
                "world": manifest["simulation"]["world"],
            }
            print(values[args.field])
        elif args.command == "launch":
            manifest = load_manifest(args.manifest.resolve())
            os.execvp("ros2", launch_command(manifest))
        elif args.command == "run":
            manifest, scenario = validate_contract(args.manifest, args.scenario)
            run_scenario(manifest, scenario)
            print(f"Scenario {scenario['name']} passed.")
    except (ConfigurationError, OSError, RuntimeError, TimeoutError) as error:
        print(f"drn-project: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
