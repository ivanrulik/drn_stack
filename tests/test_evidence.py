"""Focused tests for bounded, portable DRN evidence packs."""

import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "docker" / "evidence.py"
SPEC = importlib.util.spec_from_file_location("drn_evidence", MODULE_PATH)
EVIDENCE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(EVIDENCE)


class EvidenceFixture:
    """Create a minimal evidence directory with valid binary signatures."""

    def __init__(self, root: Path, run_id: str = "run-one") -> None:
        self.root = root / run_id
        for directory in ("logs", "metadata", "state", "telemetry", "ulog"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        (self.root / "metadata" / "compose.yaml").write_text(
            """services:
  ros-viz:
    build:
      args:
        PX4_MSGS_REF: abc123
  px4-sitl:
    build:
      args:
        PX4_REF: def456
""",
            encoding="utf-8",
        )
        (self.root / "metadata" / "project.yaml").write_text(
            "schema_version: 1\nname: test-project\n", encoding="utf-8"
        )
        (self.root / "metadata" / "scenario.yaml").write_text(
            "schema_version: 1\nname: startup-health\n", encoding="utf-8"
        )
        (self.root / "state" / "recorder.json").write_text(
            json.dumps(
                {
                    "max_bag_file_bytes": EVIDENCE.MAX_BAG_FILE_BYTES,
                    "message_count": 2,
                    "recorded_topics": ["/fmu/out/vehicle_status"],
                    "storage": "mcap",
                    "storage_preset_profile": "zstd_fast",
                    "topics": ["/clock", "/fmu/out/vehicle_status"],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "telemetry" / "telemetry_0.mcap").write_bytes(
            EVIDENCE.MCAP_MAGIC + b"telemetry"
        )
        (self.root / "telemetry" / "metadata.yaml").write_text(
            """rosbag2_bagfile_information:
  storage_identifier: mcap
  message_count: 2
  topics_with_message_count:
    - topic_metadata:
        name: /fmu/out/vehicle_status
      message_count: 2
""",
            encoding="utf-8",
        )
        ulog = self.root / "ulog" / "2026-08-01" / "run.ulg"
        ulog.parent.mkdir()
        ulog.write_bytes(EVIDENCE.ULOG_MAGIC + b"flight-data")
        (self.root / "logs" / "scenario.log").write_text(
            "Scenario passed.\n", encoding="utf-8"
        )

    def finalize(self, verdict: str = "passed"):
        return EVIDENCE.finalize_pack(
            self.root,
            run_id=self.root.name,
            project_name="test-project",
            scenario_name="startup-health",
            verdict=verdict,
            started_at="2026-08-01T00:00:00Z",
            finished_at="2026-08-01T00:01:00Z",
            git_revision="0123456789abcdef",
            ros_image="drn-stack/test-project:humble",
            ros_image_id="sha256:ros",
            px4_image="drn-stack/px4-sitl:v1.17.0",
            px4_image_id="sha256:px4",
            vehicle="gz_x500",
            world="default",
            ros_domain_id="0",
        )


class EvidenceTests(unittest.TestCase):
    """Validate completeness, integrity, bounds, and safe retention."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_finalize_and_validate_complete_pack(self):
        fixture = EvidenceFixture(self.root)
        manifest = fixture.finalize()
        validated = EVIDENCE.validate_pack(fixture.root)

        self.assertEqual("passed", manifest["result"]["verdict"])
        self.assertEqual("drn.evidence/v1", validated["schema"])
        self.assertEqual("abc123", validated["software"]["pins"]["PX4_MSGS_REF"])
        self.assertEqual("def456", validated["software"]["pins"]["PX4_REF"])
        self.assertEqual(1, len(validated["capture"]["mcap_files"]))
        self.assertEqual(1, len(validated["capture"]["ulog_files"]))

    def test_checksum_tampering_is_rejected(self):
        fixture = EvidenceFixture(self.root)
        fixture.finalize()
        (fixture.root / "logs" / "scenario.log").write_text(
            "changed\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            EVIDENCE.EvidenceError, "(size|checksum) mismatch"
        ):
            EVIDENCE.validate_pack(fixture.root)

    def test_success_requires_mcap_and_ulog(self):
        fixture = EvidenceFixture(self.root)
        for path in (fixture.root / "ulog").rglob("*.ulg"):
            path.unlink()
        with self.assertRaisesRegex(EVIDENCE.EvidenceError, "no PX4 ULog"):
            fixture.finalize()
        manifest = json.loads(
            (fixture.root / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual("failed", manifest["result"]["verdict"])

    def test_success_rejects_zero_message_mcap(self):
        fixture = EvidenceFixture(self.root)
        (fixture.root / "telemetry" / "metadata.yaml").write_text(
            """rosbag2_bagfile_information:
  storage_identifier: mcap
  message_count: 0
  topics_with_message_count: []
""",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(EVIDENCE.EvidenceError, "contains no messages"):
            fixture.finalize()

    def test_declared_pack_size_is_enforced(self):
        fixture = EvidenceFixture(self.root)
        with self.assertRaisesRegex(EVIDENCE.EvidenceError, "exceeds limit"):
            EVIDENCE.finalize_pack(
                fixture.root,
                run_id=fixture.root.name,
                project_name="test-project",
                scenario_name="startup-health",
                verdict="passed",
                started_at="2026-08-01T00:00:00Z",
                finished_at="2026-08-01T00:01:00Z",
                git_revision="0123456789abcdef",
                ros_image="drn-stack/test-project:humble",
                ros_image_id="sha256:ros",
                px4_image="drn-stack/px4-sitl:v1.17.0",
                px4_image_id="sha256:px4",
                vehicle="gz_x500",
                world="default",
                ros_domain_id="0",
                max_pack_bytes=1,
            )

    def test_failed_run_can_preserve_partial_evidence(self):
        run_dir = self.root / "failed-run"
        (run_dir / "metadata").mkdir(parents=True)
        for name, text in (
            ("compose.yaml", "services: {}\n"),
            ("project.yaml", "schema_version: 1\nname: test\n"),
            ("scenario.yaml", "schema_version: 1\nname: startup-health\n"),
        ):
            (run_dir / "metadata" / name).write_text(text, encoding="utf-8")

        EVIDENCE.finalize_pack(
            run_dir,
            run_id="failed-run",
            project_name="test",
            scenario_name="startup-health",
            verdict="failed",
            started_at="2026-08-01T00:00:00Z",
            finished_at="2026-08-01T00:00:10Z",
            git_revision="0123456789abcdef",
            ros_image="unavailable",
            ros_image_id="unavailable",
            px4_image="drn-stack/px4-sitl:v1.17.0",
            px4_image_id="unavailable",
            vehicle="gz_x500",
            world="default",
            ros_domain_id="0",
            error="stack startup failed",
        )
        manifest = EVIDENCE.validate_pack(run_dir)
        self.assertEqual("failed", manifest["result"]["verdict"])
        self.assertTrue(
            any(
                "recorder metadata" in error
                for error in manifest["result"]["capture_errors"]
            )
        )

    def test_retention_only_removes_recognized_old_packs(self):
        fixtures = []
        for index in range(3):
            fixture = EvidenceFixture(self.root, f"run-{index}")
            fixture.finalize()
            os.utime(fixture.root, (index + 1, index + 1))
            fixtures.append(fixture)
        unknown = self.root / "user-notes"
        unknown.mkdir()
        (unknown / "keep.txt").write_text("keep\n", encoding="utf-8")

        removed = EVIDENCE.prune_packs(self.root, keep=2)

        self.assertEqual([fixtures[0].root], removed)
        self.assertFalse(fixtures[0].root.exists())
        self.assertTrue(fixtures[1].root.exists())
        self.assertTrue(fixtures[2].root.exists())
        self.assertTrue(unknown.exists())


if __name__ == "__main__":
    unittest.main()
