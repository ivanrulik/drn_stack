"""Focused tests for the inert DRN project extension contract."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "docker" / "project-sdk.py"
SPEC = importlib.util.spec_from_file_location("drn_project_sdk", MODULE_PATH)
SDK = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(SDK)


def valid_manifest() -> dict:
    """Return a minimal valid project manifest."""
    return {
        "schema_version": 1,
        "name": "test-project",
        "simulation": {"vehicle": "gz_x500", "world": "default"},
        "launch": {
            "package": "test_project",
            "file": "test.launch.py",
            "arguments": {"enabled": True, "rate": 2.0},
        },
        "health": {
            "nodes": ["/test_project"],
            "topics": ["/test/heartbeat"],
            "services": [],
        },
        "scenarios": ["startup-health"],
    }


def valid_scenario() -> dict:
    """Return a minimal valid inert scenario."""
    return {
        "schema_version": 1,
        "name": "startup-health",
        "timeout_seconds": 30,
        "setup": [{"type": "core-smoke"}],
        "actions": [],
        "assertions": [
            {"type": "project-health"},
            {"type": "topic-message", "name": "/test/heartbeat"},
        ],
        "cleanup": [{"type": "stop-stack"}],
    }


class ContractFixture:
    """Create a temporary project using the real contract layout."""

    def __init__(self, root: Path, manifest: dict, scenario: dict) -> None:
        self.root = root
        self.manifest_path = root / "project.yaml"
        self.scenario_path = root / "scenarios" / "startup-health.yaml"
        package_root = root / "ros_ws" / "src" / "test_project"
        package_root.mkdir(parents=True)
        self.scenario_path.parent.mkdir()
        (package_root / "package.xml").write_text(
            """<?xml version="1.0"?>
<package format="3">
  <name>test_project</name>
  <version>0.1.0</version>
  <description>Test project.</description>
  <maintainer email="test@example.com">Test</maintainer>
  <license>MIT</license>
</package>
""",
            encoding="utf-8",
        )
        self.manifest_path.write_text(
            yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
        )
        self.scenario_path.write_text(
            yaml.safe_dump(scenario, sort_keys=False), encoding="utf-8"
        )
        (root / "compose.override.yaml").write_text(
            """services:
  ros-viz:
    image: drn-stack/test-project:humble
    build:
      context: ${DRN_PROJECT_DIR:?Set DRN_PROJECT_DIR to the absolute project directory}
      dockerfile: Dockerfile
    environment:
      DRN_PROJECT_MANIFEST: /opt/drn_project/project.yaml
    volumes:
      - type: bind
        source: ${DRN_PROJECT_DIR:?Set DRN_PROJECT_DIR to the absolute project directory}
        target: /opt/drn_project
        read_only: true
""",
            encoding="utf-8",
        )


class ProjectSdkTests(unittest.TestCase):
    """Validate strict schema and safety boundaries."""

    def make_fixture(self, manifest=None, scenario=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return ContractFixture(
            Path(temporary.name),
            manifest or valid_manifest(),
            scenario or valid_scenario(),
        )

    def test_valid_contract_and_launch_command(self):
        fixture = self.make_fixture()
        manifest, scenario = SDK.validate_contract(
            fixture.manifest_path, fixture.scenario_path
        )
        self.assertEqual("startup-health", scenario["name"])
        self.assertEqual(
            [
                "ros2",
                "launch",
                "test_project",
                "test.launch.py",
                "enabled:=true",
                "rate:=2.0",
            ],
            SDK.launch_command(manifest),
        )

    def test_nonempty_actions_are_rejected(self):
        scenario = valid_scenario()
        scenario["actions"] = [{"type": "arm"}]
        fixture = self.make_fixture(scenario=scenario)
        with self.assertRaisesRegex(SDK.ConfigurationError, "actions must be an empty"):
            SDK.validate_contract(fixture.manifest_path, fixture.scenario_path)

    def test_unknown_manifest_key_is_rejected(self):
        manifest = valid_manifest()
        manifest["command"] = "echo unsafe"
        fixture = self.make_fixture(manifest=manifest)
        with self.assertRaisesRegex(SDK.ConfigurationError, "unknown keys: command"):
            SDK.validate_contract(fixture.manifest_path, fixture.scenario_path)

    def test_compose_override_cannot_change_core_services(self):
        fixture = self.make_fixture()
        override_path = fixture.root / "compose.override.yaml"
        override_path.write_text(
            override_path.read_text(encoding="utf-8")
            + "  px4-sitl:\n    privileged: true\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SDK.ConfigurationError, "unknown keys: px4-sitl"):
            SDK.validate_contract(fixture.manifest_path, fixture.scenario_path)

    def test_topic_message_must_be_declared_health_signal(self):
        scenario = valid_scenario()
        scenario["assertions"][1]["name"] = "/undeclared/topic"
        fixture = self.make_fixture(scenario=scenario)
        with self.assertRaisesRegex(SDK.ConfigurationError, "health.topics"):
            SDK.validate_contract(fixture.manifest_path, fixture.scenario_path)

    def test_underlay_override_is_rejected(self):
        manifest = valid_manifest()
        manifest["launch"]["package"] = "drn_control"
        fixture = self.make_fixture(manifest=manifest)
        package_path = fixture.root / "ros_ws" / "src" / "test_project" / "package.xml"
        package_path.write_text(
            package_path.read_text(encoding="utf-8").replace(
                "<name>test_project</name>", "<name>drn_control</name>"
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(SDK.ConfigurationError, "must extend, not override"):
            SDK.validate_contract(fixture.manifest_path, fixture.scenario_path)

    def test_scenario_outside_contract_directory_is_rejected(self):
        fixture = self.make_fixture()
        outside_path = fixture.root / "startup-health.yaml"
        outside_path.write_text(
            fixture.scenario_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        with self.assertRaisesRegex(SDK.ConfigurationError, "scenarios directory"):
            SDK.validate_contract(fixture.manifest_path, outside_path)


if __name__ == "__main__":
    unittest.main()
