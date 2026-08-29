"""Host-side QGroundControl diagnostic tests."""

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
BASH_DOCTOR = REPO_ROOT / 'scripts' / 'qgc-doctor.sh'
POWERSHELL_DOCTOR = REPO_ROOT / 'scripts' / 'qgc-doctor.ps1'


class QgcDoctorTests(unittest.TestCase):
    """Keep QGC diagnosis read-only, port-aware, and cross-platform."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bin_dir = Path(self.temp_dir.name)
        self._write_command(
            'docker',
            r'''
            case "${1:-}" in
              info) exit 0 ;;
              ps) echo 'abc123' ;;
              inspect) echo 'drn-stack_default 172.18.0.2 172.18.0.1' ;;
              network) echo '172.18.0.0/16' ;;
              *) exit 2 ;;
            esac
            ''',
        )
        self._write_command(
            'ss',
            r'''echo "UNCONN 0 0 0.0.0.0:${QGC_PORT:-14550} 0.0.0.0:*" ''',
        )
        self._write_command('systemctl', 'exit 0')
        self._write_command('journalctl', 'exit 0')

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_command(self, name, body):
        path = self.bin_dir / name
        path.write_text(
            '#!/usr/bin/env bash\n'
            + textwrap.dedent(body).strip()
            + '\n',
            encoding='utf-8',
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def _run_doctor(self, **environment):
        env = os.environ.copy()
        env.update(environment)
        env['PATH'] = f'{self.bin_dir}:{env["PATH"]}'
        return subprocess.run(
            ['bash', str(BASH_DOCTOR)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )

    def test_reports_listener_and_prints_but_does_not_apply_ufw_rule(self):
        marker = self.bin_dir / 'sudo-was-called'
        self._write_command('sudo', f'touch {marker!s}')

        result = self._run_doctor()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS: a host process is listening on UDP 14550', result.stdout)
        self.assertIn(
            'sudo ufw allow in from 172.18.0.0/16 to 172.18.0.1 port 14550',
            result.stdout,
        )
        self.assertIn('The command is not executed by this script', result.stdout)
        self.assertFalse(marker.exists())

    def test_reports_matching_recent_ufw_drop_as_failure(self):
        self._write_command(
            'journalctl',
            "echo '[UFW BLOCK] SRC=172.18.0.2 DST=172.18.0.1 PROTO=UDP SPT=18570 DPT=14550'",
        )

        result = self._run_doctor()

        self.assertEqual(result.returncode, 1)
        self.assertIn('recent kernel logs show UFW blocking', result.stderr)
        self.assertIn('SRC=172.18.0.2', result.stderr)

    def test_custom_port_is_validated_before_docker_is_used(self):
        result = self._run_doctor(QGC_PORT='not-a-port')

        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid QGC_PORT 'not-a-port'", result.stderr)

    def test_custom_port_is_used_in_listener_and_firewall_checks(self):
        result = self._run_doctor(QGC_PORT='14551')

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('listening on UDP 14551', result.stdout)
        self.assertIn('port 14551 proto udp', result.stdout)

    def test_loopback_only_listener_is_not_reported_as_reachable(self):
        self._write_command(
            'ss',
            r'''echo 'UNCONN 0 0 127.0.0.1:14550 0.0.0.0:*' ''',
        )

        result = self._run_doctor()

        self.assertEqual(result.returncode, 1)
        self.assertIn(
            'listening only on an address Docker cannot reach',
            result.stderr,
        )

    def test_scripts_and_startup_summaries_remain_behaviorally_aligned(self):
        powershell = POWERSHELL_DOCTOR.read_text(encoding='utf-8')
        bash = BASH_DOCTOR.read_text(encoding='utf-8')
        bash_lifecycle = (REPO_ROOT / 'scripts' / 'simctl.sh').read_text(
            encoding='utf-8'
        )
        powershell_lifecycle = (
            REPO_ROOT / 'scripts' / 'simctl.ps1'
        ).read_text(encoding='utf-8')

        for script in (bash, powershell):
            self.assertIn('QGC_PORT', script)
            self.assertIn('host.docker.internal', script)
            self.assertIn('drn-stack', script)
            self.assertNotIn('ufw disable', script)
        self.assertIn('qgc-doctor.sh', bash_lifecycle)
        self.assertIn('qgc-doctor.ps1', powershell_lifecycle)


if __name__ == '__main__':
    unittest.main()
