"""Regression tests for Docker Desktop storage recovery."""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class StorageGuardrailTests(unittest.TestCase):
    """Keep VHDX recovery deterministic and safe for existing Docker data."""

    @classmethod
    def setUpClass(cls):
        cls.script = (REPO_ROOT / 'scripts/reclaim-docker-space.ps1').read_text(
            encoding='utf-8'
        )

    def test_reclaim_works_when_docker_desktop_is_already_stopped(self):
        self.assertIn('$DockerWasRunning = $LASTEXITCODE -eq 0', self.script)
        self.assertIn('if ($DockerWasRunning) {', self.script)
        self.assertNotIn("throw 'Docker Desktop is not running.'", self.script)

    def test_reclaim_explicitly_compacts_the_dynamic_vhdx(self):
        self.assertIn("'compact vdisk'", self.script)
        self.assertIn('Wait-VhdUnlocked -Path $Path', self.script)

    def test_reclaim_preserves_the_initial_docker_desktop_state(self):
        self.assertIn(
            'Docker Desktop remains stopped, matching its initial state.',
            self.script,
        )
        self.assertIn('No Docker data was pruned.', self.script)


if __name__ == '__main__':
    unittest.main()
