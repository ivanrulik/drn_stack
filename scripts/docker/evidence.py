#!/usr/bin/env python3
"""Create, validate, record, and replay bounded DRN evidence packs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

import yaml


SCHEMA_VERSION = 1
SCHEMA_NAME = "drn.evidence/v1"
MCAP_MAGIC = b"\x89MCAP0\r\n"
ULOG_MAGIC = b"ULog\x01\x12\x35"
MAX_BAG_FILE_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_PACK_BYTES = 1024 * 1024 * 1024
DEFAULT_RETENTION_COUNT = 5
CORE_TOPICS = (
    "/clock",
    "/fmu/out/battery_status_v1",
    "/fmu/out/vehicle_command_ack",
    "/fmu/out/vehicle_local_position",
    "/fmu/out/vehicle_odometry",
    "/fmu/out/vehicle_status",
    "/joint_states",
    "/robot_description",
    "/tf",
    "/tf_static",
)


class EvidenceError(RuntimeError):
    """Raised when an evidence pack is invalid or incomplete."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise EvidenceError(f"could not read YAML file {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"YAML file must contain a mapping: {path}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceError(f"could not read JSON file {path}: {error}") from error
    if not isinstance(value, dict):
        raise EvidenceError(f"JSON file must contain an object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_files(run_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in run_dir.rglob("*")
        if path.is_file()
        and path.name not in {"manifest.json", "recorder.pid"}
        and not path.name.endswith(".tmp")
    )


def _validate_magic(path: Path, expected: bytes, label: str) -> None:
    try:
        with path.open("rb") as stream:
            actual = stream.read(len(expected))
    except OSError as error:
        raise EvidenceError(f"could not read {label} file {path}: {error}") from error
    if actual != expected:
        raise EvidenceError(f"{path} is not a valid {label} file")


def _manifest_topics(project_manifest: Path) -> list[str]:
    manifest = _load_yaml(project_manifest)
    health = manifest.get("health")
    topics = health.get("topics") if isinstance(health, dict) else None
    if not isinstance(topics, list) or not all(isinstance(item, str) for item in topics):
        raise EvidenceError("project manifest health.topics must be a string list")
    return sorted(set(CORE_TOPICS).union(topics))


def _rosbag_metadata(telemetry_dir: Path) -> dict[str, Any]:
    metadata = _load_yaml(telemetry_dir / "metadata.yaml")
    information = metadata.get("rosbag2_bagfile_information")
    if not isinstance(information, dict):
        raise EvidenceError("rosbag metadata has no bagfile information")
    if information.get("storage_identifier") != "mcap":
        raise EvidenceError("rosbag metadata does not identify MCAP storage")
    message_count = information.get("message_count")
    if not isinstance(message_count, int) or message_count <= 0:
        raise EvidenceError("MCAP telemetry contains no messages")
    return information


def start_recording(run_dir: Path, project_manifest: Path) -> None:
    """Start an MCAP recorder in a detached process group."""
    run_dir = run_dir.resolve()
    telemetry_dir = run_dir / "telemetry"
    log_dir = run_dir / "logs"
    state_dir = run_dir / "state"
    if telemetry_dir.exists():
        raise EvidenceError(f"telemetry output already exists: {telemetry_dir}")
    log_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    pid_path = state_dir / "recorder.pid"
    if pid_path.exists():
        raise EvidenceError(f"recorder state already exists: {pid_path}")

    topics = _manifest_topics(project_manifest)
    command = [
        "ros2",
        "bag",
        "record",
        "--storage",
        "mcap",
        "--storage-preset-profile",
        "zstd_fast",
        "--max-bag-size",
        str(MAX_BAG_FILE_BYTES),
        "--output",
        str(telemetry_dir),
        *topics,
    ]
    log_path = log_dir / "rosbag-record.log"
    with log_path.open("ab", buffering=0) as log_stream:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    time.sleep(1.0)
    return_code = process.poll()
    if return_code is not None:
        raise EvidenceError(
            f"rosbag recorder exited during startup with code {return_code}; "
            f"see {log_path}"
        )

    pid_path.write_text(f"{process.pid}\n", encoding="ascii")
    _write_json(
        state_dir / "recorder.json",
        {
            "command": command,
            "max_bag_file_bytes": MAX_BAG_FILE_BYTES,
            "pid": process.pid,
            "started_at": _utc_now(),
            "storage": "mcap",
            "storage_preset_profile": "zstd_fast",
            "topics": topics,
        },
    )


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def stop_recording(run_dir: Path, timeout_seconds: float = 30.0) -> None:
    """Finalize the detached MCAP recorder and save rosbag metadata."""
    run_dir = run_dir.resolve()
    pid_path = run_dir / "state" / "recorder.pid"
    if not pid_path.is_file():
        raise EvidenceError(f"recorder state was not found: {pid_path}")
    try:
        pid = int(pid_path.read_text(encoding="ascii").strip())
    except (OSError, UnicodeError, ValueError) as error:
        raise EvidenceError(f"invalid recorder PID file: {pid_path}") from error
    if pid <= 1:
        raise EvidenceError(f"refusing to signal invalid recorder PID {pid}")

    if _process_exists(pid):
        try:
            os.killpg(pid, signal.SIGINT)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + timeout_seconds
        while _process_exists(pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        if _process_exists(pid):
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            raise EvidenceError("rosbag recorder did not stop cleanly after SIGINT")
    pid_path.unlink(missing_ok=True)

    telemetry_dir = run_dir / "telemetry"
    mcap_files = sorted(telemetry_dir.glob("*.mcap"))
    if not mcap_files:
        raise EvidenceError(f"no MCAP file was produced under {telemetry_dir}")
    for path in mcap_files:
        _validate_magic(path, MCAP_MAGIC, "MCAP")

    info = subprocess.run(
        ["ros2", "bag", "info", str(telemetry_dir)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    info_text = info.stdout + info.stderr
    (run_dir / "logs" / "rosbag-info.txt").write_text(info_text, encoding="utf-8")
    if info.returncode != 0:
        raise EvidenceError(
            f"ros2 bag info failed with code {info.returncode}; "
            "see logs/rosbag-info.txt"
        )
    bag_information = _rosbag_metadata(telemetry_dir)
    recorder_path = run_dir / "state" / "recorder.json"
    recorder = _load_json(recorder_path)
    recorder["message_count"] = bag_information["message_count"]
    recorder["recorded_topics"] = sorted(
        topic["topic_metadata"]["name"]
        for topic in bag_information.get("topics_with_message_count", [])
        if isinstance(topic, dict)
        and isinstance(topic.get("topic_metadata"), dict)
        and isinstance(topic["topic_metadata"].get("name"), str)
        and isinstance(topic.get("message_count"), int)
        and topic["message_count"] > 0
    )
    recorder["stopped_at"] = _utc_now()
    _write_json(recorder_path, recorder)


def _software_pins(compose_path: Path) -> dict[str, str]:
    compose = _load_yaml(compose_path)
    services = compose.get("services")
    if not isinstance(services, dict):
        raise EvidenceError("captured Compose file has no services mapping")
    pins: dict[str, str] = {}
    for service in services.values():
        if not isinstance(service, dict):
            continue
        build = service.get("build")
        args = build.get("args") if isinstance(build, dict) else None
        if not isinstance(args, dict):
            continue
        for name, value in args.items():
            if isinstance(name, str) and name.endswith("_REF") and isinstance(value, str):
                pins[name] = value
    return dict(sorted(pins.items()))


def _capture_inventory(run_dir: Path) -> tuple[list[dict[str, Any]], int]:
    inventory = []
    total_size = 0
    for path in _relative_files(run_dir):
        size = path.stat().st_size
        total_size += size
        inventory.append(
            {
                "path": path.relative_to(run_dir).as_posix(),
                "sha256": _sha256(path),
                "size_bytes": size,
            }
        )
    return inventory, total_size


def finalize_pack(
    run_dir: Path,
    *,
    run_id: str,
    project_name: str,
    scenario_name: str,
    verdict: str,
    started_at: str,
    finished_at: str,
    git_revision: str,
    ros_image: str,
    ros_image_id: str,
    px4_image: str,
    px4_image_id: str,
    vehicle: str,
    world: str,
    ros_domain_id: str,
    error: str | None = None,
    max_pack_bytes: int = DEFAULT_MAX_PACK_BYTES,
) -> dict[str, Any]:
    """Write a portable result and checksummed evidence manifest."""
    run_dir = run_dir.resolve()
    if verdict not in {"passed", "failed"}:
        raise EvidenceError(f"unsupported verdict: {verdict}")
    if max_pack_bytes <= 0:
        raise EvidenceError("max_pack_bytes must be positive")

    metadata_dir = run_dir / "metadata"
    compose_path = metadata_dir / "compose.yaml"
    project_path = metadata_dir / "project.yaml"
    scenario_path = metadata_dir / "scenario.yaml"
    for path in (compose_path, project_path, scenario_path):
        if not path.is_file():
            raise EvidenceError(f"required captured input is missing: {path}")

    capture_errors = []
    recorder_path = run_dir / "state" / "recorder.json"
    if recorder_path.is_file():
        recorder = _load_json(recorder_path)
    else:
        recorder = {}
        capture_errors.append("recorder metadata was not captured")
    mcap_files = sorted((run_dir / "telemetry").glob("*.mcap"))
    ulog_files = sorted((run_dir / "ulog").rglob("*.ulg"))
    if not mcap_files:
        capture_errors.append("no MCAP file was captured")
    if not ulog_files:
        capture_errors.append("no PX4 ULog file was captured")
    for path in mcap_files:
        try:
            _validate_magic(path, MCAP_MAGIC, "MCAP")
        except EvidenceError as capture_error:
            capture_errors.append(str(capture_error))
    if mcap_files:
        try:
            _rosbag_metadata(run_dir / "telemetry")
        except EvidenceError as capture_error:
            capture_errors.append(str(capture_error))
    for path in ulog_files:
        try:
            _validate_magic(path, ULOG_MAGIC, "ULog")
        except EvidenceError as capture_error:
            capture_errors.append(str(capture_error))

    effective_verdict = verdict
    effective_error = error
    if capture_errors and verdict == "passed":
        effective_verdict = "failed"
        effective_error = "; ".join(capture_errors)
    result = {
        "capture_errors": capture_errors,
        "error": effective_error,
        "finished_at": finished_at,
        "started_at": started_at,
        "verdict": effective_verdict,
    }
    _write_json(run_dir / "result.json", result)

    inventory, total_size = _capture_inventory(run_dir)
    if total_size > max_pack_bytes:
        result["verdict"] = "failed"
        result["error"] = (
            f"evidence pack size {total_size} exceeds limit {max_pack_bytes}"
        )
        _write_json(run_dir / "result.json", result)
        inventory, total_size = _capture_inventory(run_dir)

    manifest = {
        "capture": {
            "max_bag_file_bytes": recorder.get("max_bag_file_bytes"),
            "max_pack_bytes": max_pack_bytes,
            "mcap_files": [path.relative_to(run_dir).as_posix() for path in mcap_files],
            "message_count": recorder.get("message_count"),
            "recorded_topics": recorder.get("recorded_topics"),
            "storage": recorder.get("storage"),
            "storage_preset_profile": recorder.get("storage_preset_profile"),
            "topics": recorder.get("topics"),
            "ulog_files": [path.relative_to(run_dir).as_posix() for path in ulog_files],
        },
        "environment": {
            "ros_domain_id": ros_domain_id,
            "vehicle": vehicle,
            "world": world,
        },
        "files": inventory,
        "project": {
            "name": project_name,
            "scenario": scenario_name,
        },
        "result": result,
        "run_id": run_id,
        "schema": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "software": {
            "drn_git_revision": git_revision,
            "pins": _software_pins(compose_path),
            "px4_image": px4_image,
            "px4_image_id": px4_image_id,
            "ros_image": ros_image,
            "ros_image_id": ros_image_id,
        },
        "total_size_bytes": total_size,
    }
    _write_json(run_dir / "manifest.json", manifest)
    if manifest["result"]["verdict"] != verdict:
        raise EvidenceError(manifest["result"]["error"] or "evidence capture failed")
    return manifest


def validate_pack(run_dir: Path) -> dict[str, Any]:
    """Validate schema, bounds, file hashes, and telemetry file signatures."""
    run_dir = run_dir.resolve()
    manifest = _load_json(run_dir / "manifest.json")
    if manifest.get("schema") != SCHEMA_NAME:
        raise EvidenceError(f"unsupported evidence schema: {manifest.get('schema')!r}")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError(
            f"unsupported evidence schema_version: {manifest.get('schema_version')!r}"
        )
    files = manifest.get("files")
    if not isinstance(files, list):
        raise EvidenceError("manifest files must be a list")

    total_size = 0
    inventory_paths = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise EvidenceError("manifest file entry must be an object")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative:
            raise EvidenceError("manifest file path must be a non-empty string")
        path = (run_dir / relative).resolve()
        try:
            path.relative_to(run_dir)
        except ValueError as error:
            raise EvidenceError(f"manifest path escapes the evidence pack: {relative}") from error
        if not path.is_file():
            raise EvidenceError(f"manifest file is missing: {relative}")
        size = path.stat().st_size
        if size != entry.get("size_bytes"):
            raise EvidenceError(f"manifest size mismatch: {relative}")
        if _sha256(path) != entry.get("sha256"):
            raise EvidenceError(f"manifest checksum mismatch: {relative}")
        total_size += size
        inventory_paths.add(relative)

    if total_size != manifest.get("total_size_bytes"):
        raise EvidenceError("manifest total_size_bytes does not match the file inventory")
    capture = manifest.get("capture")
    if not isinstance(capture, dict):
        raise EvidenceError("manifest capture must be an object")
    max_pack_bytes = capture.get("max_pack_bytes")
    if not isinstance(max_pack_bytes, int) or total_size > max_pack_bytes:
        raise EvidenceError("evidence pack exceeds its declared size limit")

    mcap_files = capture.get("mcap_files")
    ulog_files = capture.get("ulog_files")
    if not isinstance(mcap_files, list) or not all(
        isinstance(relative, str) for relative in mcap_files
    ):
        raise EvidenceError("manifest MCAP files must be a string list")
    if not isinstance(ulog_files, list) or not all(
        isinstance(relative, str) for relative in ulog_files
    ):
        raise EvidenceError("manifest ULog files must be a string list")
    if mcap_files:
        message_count = capture.get("message_count")
        if not isinstance(message_count, int) or message_count <= 0:
            raise EvidenceError("manifest MCAP message count must be positive")
        _rosbag_metadata(run_dir / "telemetry")
    for relative in mcap_files:
        if relative not in inventory_paths:
            raise EvidenceError(f"MCAP file is not in the inventory: {relative}")
        _validate_magic(run_dir / relative, MCAP_MAGIC, "MCAP")
    for relative in ulog_files:
        if relative not in inventory_paths:
            raise EvidenceError(f"ULog file is not in the inventory: {relative}")
        _validate_magic(run_dir / relative, ULOG_MAGIC, "ULog")
    return manifest


def prune_packs(root: Path, keep: int) -> list[Path]:
    """Remove only recognized, finalized evidence directories beyond retention."""
    root = root.resolve()
    if keep < 1:
        raise EvidenceError("retention count must be at least 1")
    if not root.is_dir():
        return []
    candidates = []
    for path in root.iterdir():
        manifest_path = path / "manifest.json"
        if not path.is_dir() or not manifest_path.is_file():
            continue
        try:
            manifest = _load_json(manifest_path)
        except EvidenceError:
            continue
        if manifest.get("schema") == SCHEMA_NAME and manifest.get("run_id") == path.name:
            candidates.append(path)
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    removed = []
    for path in candidates[keep:]:
        shutil.rmtree(path)
        removed.append(path)
    return removed


def _port_is_listening(port: int) -> bool:
    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        try:
            lines = table.read_text(encoding="ascii").splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) >= 4:
                local_port = int(fields[1].rsplit(":", 1)[1], 16)
                if local_port == port and fields[3] == "0A":
                    return True
    return False


def replay_pack(run_dir: Path, port: int) -> None:
    """Replay MCAP telemetry through a read-only Foxglove bridge."""
    if port < 1 or port > 65535:
        raise EvidenceError("replay port must be an integer from 1 to 65535")
    manifest = validate_pack(run_dir)
    mcap_files = manifest["capture"]["mcap_files"]
    if not mcap_files:
        raise EvidenceError("evidence pack has no MCAP telemetry to replay")
    telemetry_dir = (run_dir / mcap_files[0]).parent
    bridge = subprocess.Popen(
        ["ros2", "launch", "drn_viz", "replay.launch.py", f"foxglove_port:={port}"],
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if bridge.poll() is not None:
                raise EvidenceError("Foxglove replay bridge exited during startup")
            if _port_is_listening(port):
                break
            time.sleep(0.2)
        else:
            raise EvidenceError("Foxglove replay bridge did not open its port")
        print(f"Replay bridge: ws://localhost:{port}", flush=True)
        subprocess.run(["ros2", "bag", "play", str(telemetry_dir)], check=True)
    finally:
        if bridge.poll() is None:
            os.killpg(bridge.pid, signal.SIGINT)
            try:
                bridge.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(bridge.pid, signal.SIGTERM)
                bridge.wait(timeout=5)


def _finalize_from_args(args: argparse.Namespace) -> None:
    finalize_pack(
        args.run_dir,
        run_id=args.run_id,
        project_name=args.project,
        scenario_name=args.scenario,
        verdict=args.verdict,
        started_at=args.started_at,
        finished_at=args.finished_at,
        git_revision=args.git_revision,
        ros_image=args.ros_image,
        ros_image_id=args.ros_image_id,
        px4_image=args.px4_image,
        px4_image_id=args.px4_image_id,
        vehicle=args.vehicle,
        world=args.world,
        ros_domain_id=args.ros_domain_id,
        error=args.error,
        max_pack_bytes=args.max_pack_bytes,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="start MCAP recording")
    start.add_argument("run_dir", type=Path)
    start.add_argument("project_manifest", type=Path)
    start.set_defaults(handler=lambda args: start_recording(args.run_dir, args.project_manifest))

    stop = subparsers.add_parser("stop", help="stop and validate MCAP recording")
    stop.add_argument("run_dir", type=Path)
    stop.set_defaults(handler=lambda args: stop_recording(args.run_dir))

    finalize = subparsers.add_parser("finalize", help="write the evidence manifest")
    finalize.add_argument("run_dir", type=Path)
    finalize.add_argument("--run-id", required=True)
    finalize.add_argument("--project", required=True)
    finalize.add_argument("--scenario", required=True)
    finalize.add_argument("--verdict", choices=("passed", "failed"), required=True)
    finalize.add_argument("--started-at", required=True)
    finalize.add_argument("--finished-at", required=True)
    finalize.add_argument("--git-revision", required=True)
    finalize.add_argument("--ros-image", required=True)
    finalize.add_argument("--ros-image-id", required=True)
    finalize.add_argument("--px4-image", required=True)
    finalize.add_argument("--px4-image-id", required=True)
    finalize.add_argument("--vehicle", required=True)
    finalize.add_argument("--world", required=True)
    finalize.add_argument("--ros-domain-id", required=True)
    finalize.add_argument("--error")
    finalize.add_argument(
        "--max-pack-bytes", type=int, default=DEFAULT_MAX_PACK_BYTES
    )
    finalize.set_defaults(handler=_finalize_from_args)

    validate = subparsers.add_parser("validate", help="validate an evidence pack")
    validate.add_argument("run_dir", type=Path)
    validate.set_defaults(handler=lambda args: validate_pack(args.run_dir))

    prune = subparsers.add_parser("prune", help="apply local evidence retention")
    prune.add_argument("root", type=Path)
    prune.add_argument("--keep", type=int, default=DEFAULT_RETENTION_COUNT)
    prune.set_defaults(handler=lambda args: prune_packs(args.root, args.keep))

    replay = subparsers.add_parser("replay", help="replay MCAP through Foxglove")
    replay.add_argument("run_dir", type=Path)
    replay.add_argument("--port", type=int, default=8765)
    replay.set_defaults(handler=lambda args: replay_pack(args.run_dir, args.port))
    return parser


def main() -> int:
    try:
        args = _parser().parse_args()
        result = args.handler(args)
        if isinstance(result, dict):
            print(json.dumps(result, sort_keys=True))
        elif isinstance(result, list):
            for path in result:
                print(path)
        return 0
    except (EvidenceError, OSError, subprocess.SubprocessError) as error:
        print(f"Evidence error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
