"""Regression tests for bounded, diagnostic CI smoke behavior."""

from pathlib import Path
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class CiSmokeTests(unittest.TestCase):
    """Keep transient discovery and earlier failures from obscuring CI results."""

    def test_ros_topic_echo_probes_supply_explicit_message_types(self):
        script = (
            REPO_ROOT / 'scripts' / 'docker' / 'smoke-test.sh'
        ).read_text(encoding='utf-8')
        normalized = ' '.join(script.replace('\\\n', ' ').split())

        expected_probes = (
            '/fmu/out/vehicle_odometry px4_msgs/msg/VehicleOdometry',
            '/robot_description std_msgs/msg/String',
            '/drn/control/status std_msgs/msg/String',
        )
        for probe in expected_probes:
            self.assertIn(probe, normalized)

    def test_evidence_upload_runs_only_when_files_exist(self):
        workflow_path = REPO_ROOT / '.github' / 'workflows' / 'docker-smoke.yml'
        workflow = yaml.safe_load(workflow_path.read_text(encoding='utf-8'))
        steps = workflow['jobs']['docker-smoke']['steps']

        detect = next(
            step for step in steps if step['name'] == 'Detect scenario evidence pack'
        )
        upload = next(
            step for step in steps if step['name'] == 'Upload scenario evidence pack'
        )

        self.assertEqual(detect['if'], 'always()')
        self.assertEqual(detect['id'], 'scenario_evidence')
        self.assertIn('find artifacts -type f', detect['run'])
        self.assertEqual(
            upload['if'],
            "always() && steps.scenario_evidence.outputs.available == 'true'",
        )
        self.assertEqual(upload['with']['if-no-files-found'], 'error')


if __name__ == '__main__':
    unittest.main()
