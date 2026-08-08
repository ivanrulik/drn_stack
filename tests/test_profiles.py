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


if __name__ == '__main__':
    unittest.main()
