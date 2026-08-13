"""Configuration and safety-contract tests for the UDP hardware profile."""

from pathlib import Path
import unittest

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


class HardwareProfileTests(unittest.TestCase):
    """Keep real-device startup explicit, read-only, and fail closed."""

    def test_compose_overlay_disables_sitl_and_binds_udp_explicitly(self):
        path = REPO_ROOT / 'connections' / 'hardware-udp' / 'compose.yaml'
        overlay = yaml.safe_load(path.read_text(encoding='utf-8'))
        ros = overlay['services']['ros-viz']
        self.assertEqual(ros['environment']['DRN_CONNECTION_MODE'], 'hardware-udp')
        ports = ros['ports']
        self.assertEqual([port['protocol'] for port in ports], ['udp', 'udp'])
        self.assertEqual(ports[0]['target'], 8888)
        self.assertEqual(ports[0]['published'], '${XRCE_PORT:-8888}')
        self.assertIn('DRN_HARDWARE_BIND_ADDRESS:?', ports[0]['host_ip'])
        self.assertIn('14580', str(ports[1]))
        self.assertNotIn('0.0.0.0', str(ports))
        self.assertEqual(
            overlay['services']['px4-sitl']['profiles'], ['sitl-only']
        )

    def test_hardware_launch_is_read_only(self):
        launch = (
            REPO_ROOT / 'src' / 'drn_viz' / 'launch' / 'hardware.launch.py'
        ).read_text(encoding='utf-8')
        self.assertNotIn("package='drn_control'", launch)
        self.assertNotIn('/drn/control/', launch)
        self.assertEqual(launch.count("'client_topic_whitelist': [r'^$']"), 1)
        self.assertEqual(launch.count("'service_whitelist': [r'^$']"), 1)
        self.assertIn("executable='odometry_tf_bridge'", launch)

    def test_entrypoint_uses_separate_hardware_launch(self):
        entrypoint = (
            REPO_ROOT / 'scripts' / 'docker' / 'ros-entrypoint.sh'
        ).read_text(encoding='utf-8')
        self.assertIn('DRN_CONNECTION_MODE:-sitl', entrypoint)
        self.assertIn('hardware.launch.py', entrypoint)
        self.assertIn('Downstream project launch is disabled', entrypoint)

    def test_lifecycle_requires_trusted_interface_and_starts_only_ros(self):
        powershell = (REPO_ROOT / 'scripts' / 'hardwarectl.ps1').read_text(
            encoding='utf-8'
        )
        bash = (REPO_ROOT / 'scripts' / 'hardwarectl.sh').read_text(
            encoding='utf-8'
        )
        for script in (powershell, bash):
            self.assertIn('DRN_HARDWARE_BIND_ADDRESS', script)
            self.assertIn('non-loopback IPv4', script)
            self.assertIn('up -d --no-build --remove-orphans', script)
            self.assertIn('ros-viz', script)
            self.assertIn('drn-hardware-smoke', script)
        self.assertNotIn('build px4-sitl', powershell)
        self.assertNotIn('build px4-sitl', bash)

    def test_acceptance_script_has_no_mutating_mavlink_commands(self):
        script = (
            REPO_ROOT / 'scripts' / 'docker' / 'hardware-smoke.py'
        ).read_text(encoding='utf-8')
        self.assertIn('MAV_CMD_REQUEST_MESSAGE', script)
        self.assertIn('param_request_read_send', script)
        for forbidden in (
            'param_set_send',
            'MAV_CMD_COMPONENT_ARM_DISARM',
            'set_mode_send',
            'command_int_send',
        ):
            self.assertNotIn(forbidden, script)


if __name__ == '__main__':
    unittest.main()
