"""Regression tests for the supported simulation profiles."""

import json
from pathlib import Path
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class SimulationProfileTests(unittest.TestCase):
    """Keep profile selection, runtime wiring, and visualization aligned."""

    def _profile(self, name):
        path = REPO_ROOT / 'profiles' / name / 'compose.yaml'
        return yaml.safe_load(path.read_text(encoding='utf-8'))

    def test_profile_directories_are_self_describing(self):
        profile_paths = sorted((REPO_ROOT / 'profiles').glob('*/compose.yaml'))
        self.assertGreaterEqual(len(profile_paths), 3)
        for path in profile_paths:
            profile = yaml.safe_load(path.read_text(encoding='utf-8'))
            ros_environment = profile['services']['ros-viz']['environment']
            self.assertEqual(ros_environment['DRN_PROFILE'], path.parent.name)
            self.assertRegex(ros_environment['DRN_AIRFRAME'], r'^[a-z0-9][a-z0-9-]*$')
            self.assertIn('DRN_PROFILE_CAPABILITIES', ros_environment)
            self.assertRegex(
                ros_environment['DRN_SIM_MODEL_NAME'],
                r'^[A-Za-z0-9][A-Za-z0-9_-]*$',
            )

    def test_basic_profile_selects_plain_x500(self):
        profile = self._profile('x500-basic')
        self.assertEqual(
            profile['services']['px4-sitl']['environment']['PX4_SIM_MODEL'],
            'gz_x500',
        )
        self.assertEqual(
            profile['services']['ros-viz']['environment']['DRN_PROFILE'],
            'x500-basic',
        )

    def test_depth_profile_selects_sensor_model(self):
        profile = self._profile('x500-depth')
        self.assertEqual(
            profile['services']['px4-sitl']['environment']['PX4_SIM_MODEL'],
            'gz_x500_depth',
        )
        self.assertEqual(
            profile['services']['ros-viz']['environment']['DRN_PROFILE'],
            'x500-depth',
        )
        self.assertEqual(
            profile['services']['ros-viz']['environment'][
                'DRN_PROFILE_CAPABILITIES'
            ],
            'depth-camera',
        )

    def test_vio_profile_selects_upstream_vision_model(self):
        profile = self._profile('x500-vio')
        self.assertEqual(
            profile['services']['px4-sitl']['environment']['PX4_SIM_MODEL'],
            'gz_x500_vision',
        )
        ros_environment = profile['services']['ros-viz']['environment']
        self.assertEqual(ros_environment['DRN_PROFILE'], 'x500-vio')
        self.assertEqual(ros_environment['DRN_AIRFRAME'], 'x500')
        self.assertEqual(
            ros_environment['DRN_PROFILE_CAPABILITIES'],
            'vision-odometry',
        )
        self.assertEqual(ros_environment['DRN_SIM_MODEL_NAME'], 'x500_vision_0')

    def test_depth_gpu_override_requests_graphics_capability(self):
        path = REPO_ROOT / 'profiles' / 'x500-depth' / 'compose.gpu.yaml'
        profile = yaml.safe_load(path.read_text(encoding='utf-8'))
        px4 = profile['services']['px4-sitl']
        self.assertEqual(px4['gpus'], 'all')
        self.assertEqual(
            px4['environment']['NVIDIA_DRIVER_CAPABILITIES'],
            'compute,graphics,utility',
        )
        self.assertEqual(
            profile['services']['ros-viz']['environment']['DRN_GPU_ACCELERATION'],
            'nvidia',
        )

    def test_depth_software_override_reduces_rates_without_changing_resolution(self):
        path = REPO_ROOT / 'profiles' / 'x500-depth' / 'compose.software.yaml'
        profile = yaml.safe_load(path.read_text(encoding='utf-8'))
        mount = profile['services']['px4-sitl']['volumes'][0]
        self.assertTrue(mount['read_only'])
        self.assertEqual(
            mount['target'],
            '/opt/PX4-Autopilot/Tools/simulation/gz/models/OakD-Lite/model.sdf',
        )

        model_path = (
            REPO_ROOT / 'profiles' / 'x500-depth' / 'models' / 'OakD-Lite' / 'model.sdf'
        )
        model = model_path.read_text(encoding='utf-8')
        self.assertIn('<width>640</width>', model)
        self.assertIn('<height>360</height>', model)
        self.assertIn('<width>640</width>', model)
        self.assertIn('<height>480</height>', model)
        self.assertIn('<update_rate>10</update_rate>', model)
        self.assertIn('<update_rate>15</update_rate>', model)

    def test_lifecycle_scripts_default_to_automatic_gpu_detection(self):
        powershell = (REPO_ROOT / 'scripts/simctl.ps1').read_text(encoding='utf-8')
        bash = (REPO_ROOT / 'scripts/simctl.sh').read_text(encoding='utf-8')
        for script in (powershell, bash):
            self.assertIn('DRN_GPU_MODE', script)
            self.assertIn('compose.gpu.yaml', script)
            self.assertIn('compose.software.yaml', script)
            self.assertIn('drn-gpu-renderer-check', script)
            self.assertIn('docker run', script)
            self.assertIn('--gpus', script)

    def test_lifecycle_scripts_discover_profiles_by_directory(self):
        powershell = (REPO_ROOT / 'scripts/simctl.ps1').read_text(encoding='utf-8')
        bash = (REPO_ROOT / 'scripts/simctl.sh').read_text(encoding='utf-8')
        self.assertIn("profiles\\$Profile", powershell)
        self.assertIn('Test-Path -LiteralPath $ProfileCompose', powershell)
        self.assertNotIn("ValidateSet('x500-basic', 'x500-depth')", powershell)
        self.assertIn('profiles/${profile}', bash)
        self.assertIn('[[ ! -f "${profile_compose}" ]]', bash)
        self.assertNotIn('x500-basic|x500-depth', bash)

    def test_ros_entrypoint_omits_empty_capability_override(self):
        entrypoint = (
            REPO_ROOT / 'scripts/docker/ros-entrypoint.sh'
        ).read_text(encoding='utf-8')
        self.assertIn('if [[ -n "${DRN_PROFILE_CAPABILITIES:-}" ]]', entrypoint)
        self.assertIn(
            'launch_args+=("capabilities:=${DRN_PROFILE_CAPABILITIES}")',
            entrypoint,
        )
        self.assertNotIn('"capabilities:=${DRN_PROFILE_CAPABILITIES:-}"', entrypoint)

    def test_gpu_check_rejects_software_renderers(self):
        check = (REPO_ROOT / 'scripts' / 'docker' / 'gpu-renderer-check.sh').read_text(
            encoding='utf-8'
        )
        self.assertIn('EGL_PLATFORM=surfaceless', check)
        self.assertIn('llvmpipe', check)
        self.assertIn('softpipe', check)

    def test_depth_layout_uses_stable_ros_topics(self):
        path = REPO_ROOT / 'foxglove' / 'drn-simulation-x500-depth.json'
        layout = json.loads(path.read_text(encoding='utf-8'))
        panels = layout['configById']
        self.assertEqual(
            panels['Image!color']['imageMode']['imageTopic'],
            '/drn/sensors/front/color/image_raw',
        )
        self.assertEqual(
            panels['Image!depth']['imageMode']['imageTopic'],
            '/drn/sensors/front/depth/image_raw',
        )
        self.assertEqual(
            panels['Image!color']['imageMode']['calibrationTopic'],
            '/drn/sensors/front/color/camera_info',
        )
        self.assertEqual(
            panels['Image!depth']['imageMode']['calibrationTopic'],
            '/drn/sensors/front/depth/camera_info',
        )

    def test_depth_launch_and_smoke_share_contract(self):
        launch = (REPO_ROOT / 'src/drn_viz/launch/visualize.launch.py').read_text(
            encoding='utf-8'
        )
        smoke = (REPO_ROOT / 'scripts/docker/sensor-smoke.py').read_text(
            encoding='utf-8'
        )
        for topic in (
            '/drn/sensors/front/color/image_raw',
            '/drn/sensors/front/depth/image_raw',
            '/drn/sensors/front/color/camera_info',
            '/drn/sensors/front/depth/camera_info',
        ):
            self.assertIn(topic, launch)
            self.assertIn(topic, smoke)

    def test_vio_launch_adapter_and_smoke_share_contract(self):
        launch = (REPO_ROOT / 'src/drn_viz/launch/visualize.launch.py').read_text(
            encoding='utf-8'
        )
        adapter = (
            REPO_ROOT / 'src/drn_viz/src/vision_odometry_adapter.cpp'
        ).read_text(encoding='utf-8')
        smoke = (
            REPO_ROOT / 'scripts/docker/vision-odometry-smoke.py'
        ).read_text(encoding='utf-8')
        for source in (launch, adapter, smoke):
            self.assertIn('/drn/sensors/vision/odometry', source)
        self.assertIn('gz.msgs.OdometryWithCovariance', launch)
        self.assertIn('/drn/internal/vision/odometry', adapter)
        self.assertIn('message->header.frame_id = world_frame_', adapter)
        self.assertIn('message->child_frame_id = base_frame_', adapter)
        self.assertIn('ARMING_STATE_DISARMED', smoke)

    def test_vio_layout_uses_stable_ros_topic(self):
        path = REPO_ROOT / 'foxglove' / 'drn-simulation-x500-vio.json'
        layout = json.loads(path.read_text(encoding='utf-8'))
        panels = layout['configById']
        self.assertEqual(
            panels['RawMessages!vision']['topicPath'],
            '/drn/sensors/vision/odometry',
        )
        for plot_path in panels['Plot!visionPosition']['paths']:
            self.assertTrue(
                plot_path['value'].startswith('/drn/sensors/vision/odometry.')
            )


if __name__ == '__main__':
    unittest.main()
