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

    def test_profile_defaults_to_two_and_passes_one_bounded_size(self):
        path = REPO_ROOT / 'profiles' / 'x500-multi' / 'compose.yaml'
        profile = yaml.safe_load(path.read_text(encoding='utf-8'))
        ros_environment = profile['services']['ros-viz']['environment']
        px4 = profile['services']['px4-sitl']

        self.assertEqual(ros_environment['DRN_PROFILE'], 'x500-multi')
        self.assertEqual(
            ros_environment['DRN_PROFILE_CAPABILITIES'], 'multi-vehicle'
        )
        self.assertEqual(
            ros_environment['DRN_FLEET_SIZE'], '${DRN_FLEET_SIZE:-2}'
        )
        self.assertEqual(px4['environment']['PX4_SIM_MODEL'], 'gz_x500')
        self.assertEqual(
            px4['environment']['DRN_FLEET_SIZE'], '${DRN_FLEET_SIZE:-2}'
        )
        self.assertEqual(
            px4['healthcheck']['test'],
            ['CMD', '/usr/local/bin/drn-fleet-healthcheck'],
        )

    def test_px4_healthcheck_requires_unique_ids_and_connected_dds(self):
        healthcheck = (
            REPO_ROOT / 'scripts' / 'docker' / 'fleet-healthcheck.sh'
        ).read_text(encoding='utf-8')

        self.assertIn('pgrep -cx px4', healthcheck)
        self.assertIn('instance <= fleet_size', healthcheck)
        self.assertIn('expected_system_id=$((instance + 1))', healthcheck)
        self.assertIn('--instance "${instance}" show MAV_SYS_ID', healthcheck)
        self.assertIn('--instance "${instance}" status', healthcheck)
        self.assertIn("grep -Fq 'Running, connected'", healthcheck)

    def test_fleet_size_contract_accepts_only_two_through_four(self):
        expected = {
            2: ('px4_1', 'px4_2'),
            3: ('px4_1', 'px4_2', 'px4_3'),
            4: ('px4_1', 'px4_2', 'px4_3', 'px4_4'),
        }
        for size, vehicles in expected.items():
            self.assertEqual(FLEET_SMOKE.fleet_vehicles(size), vehicles)
        for invalid in (1, 5, 'three', ''):
            with self.assertRaisesRegex(
                FLEET_SMOKE.FleetValidationError, 'integer from 2 through 4'
            ):
                FLEET_SMOKE.fleet_vehicles(invalid)

    def test_fleet_launch_is_namespaced_and_read_only(self):
        launch = (
            REPO_ROOT / 'src' / 'drn_viz' / 'launch' / 'fleet.launch.py'
        ).read_text(encoding='utf-8')

        self.assertIn("namespace = f'px4_{instance}'", launch)
        self.assertIn("DeclareLaunchArgument(\n            'fleet_size'", launch)
        self.assertIn('MIN_FLEET_SIZE = 2', launch)
        self.assertIn('MAX_FLEET_SIZE = 4', launch)
        self.assertIn('spawn_x = (spawn_index // 2) * 2', launch)
        self.assertIn('spawn_y = (spawn_index % 2) * 2', launch)
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
        self.assertIn('instance <= fleet_size', px4)
        self.assertIn('PX4_UXRCE_DDS_NS=px4_${instance}', px4)
        self.assertIn('instance_environment+=("PX4_GZ_STANDALONE=1")', px4)
        self.assertIn('wait_for_vehicle_odometry', px4)
        self.assertIn('did not publish odometry within 60 seconds', px4)
        self.assertIn('fleet.launch.py', ros)
        self.assertIn('fleet_size:=${DRN_FLEET_SIZE:-2}', ros)
        self.assertIn('Downstream project launch is disabled', ros)

    def test_lifecycle_accepts_count_only_for_multi_profile(self):
        powershell = (REPO_ROOT / 'scripts' / 'simctl.ps1').read_text(
            encoding='utf-8'
        )
        bash = (REPO_ROOT / 'scripts' / 'simctl.sh').read_text(encoding='utf-8')

        self.assertIn('[Nullable[int]]$VehicleCount', powershell)
        self.assertIn("$ResolvedVehicleCount -gt 4", powershell)
        self.assertIn('VehicleCount is supported only', powershell)
        self.assertIn('--vehicle-count)', bash)
        self.assertIn('vehicle_count > 4', bash)
        self.assertIn('--vehicle-count is supported only', bash)

    def test_fleet_layout_covers_all_supported_slots_without_control_panels(self):
        path = REPO_ROOT / 'foxglove' / 'drn-simulation-x500-multi.json'
        layout = json.loads(path.read_text(encoding='utf-8'))
        panels = layout['configById']

        self.assertFalse(any(name.startswith('Teleop!') for name in panels))
        for vehicle in FLEET_SMOKE.fleet_vehicles(4):
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
        vehicles = FLEET_SMOKE.fleet_vehicles(4)
        nodes = ['/foxglove_bridge']
        topics = ['/tf', '/tf_static']
        for vehicle in vehicles:
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
        with mock.patch.object(FLEET_SMOKE, 'VEHICLES', vehicles), mock.patch.object(
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
