"""Regression tests for the bounded, observation-only fleet profile."""

import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
FLEET_SMOKE_PATH = REPO_ROOT / 'scripts' / 'docker' / 'fleet-smoke.py'
SPEC = importlib.util.spec_from_file_location('fleet_smoke', FLEET_SMOKE_PATH)
FLEET_SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FLEET_SMOKE)


class FleetProfileTests(unittest.TestCase):
    """Keep fleet launch, routing, and safety contracts aligned."""

    def test_profile_is_fixed_to_two_plain_x500_instances(self):
        path = REPO_ROOT / 'profiles' / 'x500-multi' / 'compose.yaml'
        profile = yaml.safe_load(path.read_text(encoding='utf-8'))
        ros_environment = profile['services']['ros-viz']['environment']
        px4 = profile['services']['px4-sitl']

        self.assertEqual(ros_environment['DRN_PROFILE'], 'x500-multi')
        self.assertEqual(
            ros_environment['DRN_PROFILE_CAPABILITIES'], 'multi-vehicle'
        )
        self.assertEqual(
            ros_environment['DRN_FLEET_NAMESPACES'], 'px4_1,px4_2'
        )
        self.assertEqual(px4['environment']['PX4_SIM_MODEL'], 'gz_x500')
        self.assertEqual(px4['environment']['DRN_FLEET_SIZE'], '2')
        self.assertEqual(
            px4['healthcheck']['test'],
            ['CMD', '/usr/local/bin/drn-fleet-healthcheck'],
        )

    def test_px4_healthcheck_requires_unique_ids_and_connected_dds(self):
        healthcheck = (
            REPO_ROOT / 'scripts' / 'docker' / 'fleet-healthcheck.sh'
        ).read_text(encoding='utf-8')

        self.assertIn('pgrep -cx px4', healthcheck)
        self.assertIn('--instance 1 show MAV_SYS_ID', healthcheck)
        self.assertIn('--instance 2 show MAV_SYS_ID', healthcheck)
        self.assertIn("MAV_SYS_ID .*: 2$", healthcheck)
        self.assertIn("MAV_SYS_ID .*: 3$", healthcheck)
        self.assertEqual(healthcheck.count("grep -Fq 'Running, connected'"), 2)

    def test_fleet_launch_is_namespaced_and_read_only(self):
        launch = (
            REPO_ROOT / 'src' / 'drn_viz' / 'launch' / 'fleet.launch.py'
        ).read_text(encoding='utf-8')

        for namespace in ('px4_1', 'px4_2'):
            self.assertIn(namespace, launch)
            self.assertIn(f'/{namespace}/fmu/out/vehicle_odometry', launch)
        self.assertIn("'frame_prefix': f'{namespace}/'", launch)
        self.assertIn("'client_topic_whitelist': [r'^$']", launch)
        self.assertIn("'service_whitelist': [r'^$']", launch)
        self.assertNotIn("package='drn_control'", launch)

    def test_entrypoints_select_bounded_fleet_paths(self):
        px4 = (
            REPO_ROOT / 'scripts' / 'docker' / 'px4-entrypoint.sh'
        ).read_text(encoding='utf-8')
        ros = (
            REPO_ROOT / 'scripts' / 'docker' / 'ros-entrypoint.sh'
        ).read_text(encoding='utf-8')

        self.assertIn('DRN_FLEET_SIZE:-1', px4)
        self.assertIn('PX4_UXRCE_DDS_NS=px4_1', px4)
        self.assertIn('PX4_UXRCE_DDS_NS=px4_2', px4)
        self.assertIn('PX4_GZ_STANDALONE=1', px4)
        self.assertIn('fleet.launch.py', ros)
        self.assertIn('Downstream project launch is disabled', ros)

    def test_fleet_layout_has_both_vehicles_and_no_control_panels(self):
        path = REPO_ROOT / 'foxglove' / 'drn-simulation-x500-multi.json'
        layout = json.loads(path.read_text(encoding='utf-8'))
        panels = layout['configById']

        self.assertFalse(any(name.startswith('Teleop!') for name in panels))
        for vehicle in ('px4_1', 'px4_2'):
            self.assertEqual(
                panels[f'RawMessages!{vehicle}']['topicPath'],
                f'/{vehicle}/fmu/out/vehicle_status_v1',
            )
            for plot_path in panels[f'Plot!{vehicle}']['paths']:
                self.assertTrue(
                    plot_path['value'].startswith(
                        f'/{vehicle}/fmu/out/vehicle_odometry.'
                    )
                )

    def test_graph_validation_accepts_only_scoped_observation_endpoints(self):
        nodes = ['/foxglove_bridge']
        topics = ['/tf', '/tf_static']
        for vehicle in FLEET_SMOKE.VEHICLES:
            nodes.extend([
                f'/{vehicle}/map_origin',
                f'/{vehicle}/odometry_tf_bridge',
                f'/{vehicle}/robot_state_publisher',
            ])
            topics.extend([
                f'/{vehicle}/fmu/out/vehicle_odometry',
                f'/{vehicle}/fmu/out/vehicle_status_v1',
                f'/{vehicle}/robot_description',
            ])

        outputs = {
            ('node', 'list'): nodes,
            ('topic', 'list'): topics,
            ('service', 'list'): ['/foxglove_bridge/get_parameters'],
        }
        with mock.patch.object(
            FLEET_SMOKE,
            'run_ros',
            side_effect=lambda command: outputs[tuple(command)],
        ):
            FLEET_SMOKE.validate_graph()

    def test_graph_validation_rejects_unscoped_px4_topics(self):
        with mock.patch.object(FLEET_SMOKE, 'run_ros') as run_ros:
            run_ros.side_effect = [
                [
                    '/foxglove_bridge',
                    '/px4_1/map_origin',
                    '/px4_1/odometry_tf_bridge',
                    '/px4_1/robot_state_publisher',
                    '/px4_2/map_origin',
                    '/px4_2/odometry_tf_bridge',
                    '/px4_2/robot_state_publisher',
                ],
                [
                    '/fmu/out/vehicle_odometry',
                    '/px4_1/fmu/out/vehicle_odometry',
                    '/px4_1/fmu/out/vehicle_status_v1',
                    '/px4_1/robot_description',
                    '/px4_2/fmu/out/vehicle_odometry',
                    '/px4_2/fmu/out/vehicle_status_v1',
                    '/px4_2/robot_description',
                ],
                [],
            ]
            with self.assertRaisesRegex(
                FLEET_SMOKE.FleetValidationError,
                'unscoped PX4 topics',
            ):
                FLEET_SMOKE.validate_graph()


if __name__ == '__main__':
    unittest.main()
