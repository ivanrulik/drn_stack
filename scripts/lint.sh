#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Required lint tool '$1' is not installed." >&2
    exit 1
  }
}

require_command docker
require_command python3
require_command shellcheck
require_command yamllint

mapfile -t shell_files < <(find scripts -type f -name '*.sh' -print | sort)
shellcheck --external-sources "${shell_files[@]}"

mapfile -t yaml_files < <(find .github -type f \( -name '*.yaml' -o -name '*.yml' \) -print | sort)
mapfile -t project_yaml_files < <(find projects -type f \( -name '*.yaml' -o -name '*.yml' \) -print | sort)
yaml_files+=("${project_yaml_files[@]}")
mapfile -t profile_yaml_files < <(find profiles -type f \( -name '*.yaml' -o -name '*.yml' \) -print | sort)
yaml_files+=("${profile_yaml_files[@]}")
yaml_files+=(compose.yaml compose.evidence.yaml .yamllint.yml)
yamllint --strict "${yaml_files[@]}"

docker compose --project-name drn-stack --file compose.yaml config --quiet
for profile_file in profiles/*/compose.yaml; do
  docker compose \
    --project-name drn-stack \
    --file compose.yaml \
    --file "${profile_file}" \
    config --quiet
done
for gpu_file in profiles/*/compose.gpu.yaml; do
  profile_dir="$(dirname "${gpu_file}")"
  software_file="${profile_dir}/compose.software.yaml"
  [[ -f "${software_file}" ]] || {
    echo "${profile_dir} must provide compose.software.yaml with compose.gpu.yaml." >&2
    exit 1
  }
  for renderer_file in "${gpu_file}" "${software_file}"; do
    docker compose \
      --project-name drn-stack \
      --file compose.yaml \
      --file "${profile_dir}/compose.yaml" \
      --file "${renderer_file}" \
      config --quiet
  done
done
DRN_ARTIFACT_DIR=/tmp/drn-evidence docker compose \
  --project-name drn-stack \
  --file compose.yaml \
  --file compose.evidence.yaml \
  config --quiet

python3 -m compileall -q \
  src/drn_viz/launch \
  scripts/docker/evidence.py \
  scripts/docker/px4-failure.py \
  scripts/docker/project-sdk.py \
  scripts/docker/sensor-smoke.py \
  scripts/docker/vision-odometry-smoke.py \
  projects/example_inspection/ros_ws/src/drn_example_inspection
python3 -m unittest discover -s tests
python3 scripts/docker/project-sdk.py validate \
  projects/example_inspection/project.yaml \
  projects/example_inspection/scenarios/startup-health.yaml
python3 scripts/docker/project-sdk.py validate \
  projects/example_inspection/project.yaml \
  projects/example_inspection/scenarios/battery-failure.yaml
python3 - <<'PY'
import json
from pathlib import Path
from xml.etree import ElementTree

package_paths = (
    Path("src/drn_control/package.xml"),
    Path("src/drn_viz/package.xml"),
)

for path in (*package_paths, *Path("src/drn_viz/urdf").glob("*.urdf")):
    ElementTree.parse(path)
ElementTree.parse(
    Path(
        "projects/example_inspection/ros_ws/src/drn_example_inspection/package.xml"
    )
)

required_files = (
    Path("LICENSE"),
    Path("THIRD_PARTY_NOTICES.md"),
    Path("CONTRIBUTING.md"),
    Path("SUPPORT.md"),
    Path("SECURITY.md"),
    Path("docs/COMPATIBILITY.md"),
    Path("docs/RELEASE_POLICY.md"),
    Path("docs/PROJECT_SDK.md"),
    Path("docs/EVIDENCE_PACKS.md"),
    Path("src/drn_viz/meshes/LICENSE"),
)
for path in required_files:
    if not path.is_file():
        raise ValueError(f"required adoption file is missing: {path}")

expected_licenses = {
    "drn_control": {"MIT"},
    "drn_viz": {"MIT", "BSD-3-Clause"},
}
package_versions = set()
for path in package_paths:
    package = ElementTree.parse(path).getroot()
    name = package.findtext("name")
    version = package.findtext("version")
    maintainers = package.findall("maintainer")
    licenses = {element.text for element in package.findall("license")}

    if not version or version == "0.0.0":
        raise ValueError(f"{path}: package version must be a non-placeholder value")
    package_versions.add(version)

    if not maintainers:
        raise ValueError(f"{path}: at least one maintainer is required")
    for maintainer in maintainers:
        email = maintainer.attrib.get("email", "")
        if (
            not maintainer.text
            or "@" not in email
            or email.endswith("@todo.todo")
        ):
            raise ValueError(f"{path}: maintainer metadata contains a placeholder")

    if licenses != expected_licenses[name]:
        raise ValueError(
            f"{path}: expected licenses {expected_licenses[name]}, found {licenses}"
        )

if len(package_versions) != 1:
    raise ValueError(f"ROS package versions must stay synchronized: {package_versions}")

expected_refs = {
    "PX4_REF": "a5eb12d2ab591251faa009f76b2685b8cc64405d",
    "PX4_MSGS_REF": "35a005a86b82cae28bd7a2eb58c4bb7a840830c9",
    "PX4_ROS_COM_REF": "86e9aeb20e55a4673fa8a9f1c29ea06a6c5ad1af",
    "PX4_ROS2_INTERFACE_REF": "4a3370f084ac6f1ef001a4afa2b007845ffd0837",
    "MICRO_XRCE_DDS_AGENT_REF": "73622810d984349b80bbac0ef55fc0b694d62222",
    "ROS_GZ_HARMONIC_VERSION": "0.244.12-3jammy",
}
compose = Path("compose.yaml").read_text(encoding="utf-8")
compatibility = Path("docs/COMPATIBILITY.md").read_text(encoding="utf-8")
for name, revision in expected_refs.items():
    if f"{name}: {revision}" not in compose:
        raise ValueError(f"compose.yaml: expected {name} pin {revision}")
    if revision not in compatibility:
        raise ValueError(f"docs/COMPATIBILITY.md: missing {name} pin {revision}")

for path in Path("foxglove").glob("*.json"):
    with path.open(encoding="utf-8") as stream:
        layout = json.load(stream)

    panel_configs = layout["configById"]

    def validate_panel_references(node):
        if isinstance(node, str):
            if node not in panel_configs:
                raise ValueError(f"{path}: layout references missing panel {node!r}")
            return
        validate_panel_references(node["first"])
        validate_panel_references(node["second"])

    validate_panel_references(layout["layout"])

    if path.name == "drn-simulation.json":
        expected_teleop = {
            "Teleop!horizontal": "/drn/control/teleop/xy",
            "Teleop!verticalYaw": "/drn/control/teleop/z_yaw",
        }
        for panel_id, topic in expected_teleop.items():
            panel = panel_configs[panel_id]
            if panel["topic"] != topic:
                raise ValueError(f"{path}: {panel_id} must publish to {topic}")
            if panel["publishRate"] != 20 or not panel["autoSendStopOnRelease"]:
                raise ValueError(
                    f"{path}: {panel_id} must publish at 20 Hz and stop on release"
                )

    if path.name == "drn-simulation-x500-depth.json":
        expected_images = {
            "Image!color": (
                "/drn/sensors/front/color/image_raw",
                "/drn/sensors/front/color/camera_info",
            ),
            "Image!depth": (
                "/drn/sensors/front/depth/image_raw",
                "/drn/sensors/front/depth/camera_info",
            ),
        }
        for panel_id, (topic, calibration) in expected_images.items():
            panel = panel_configs[panel_id]
            if panel["imageMode"]["imageTopic"] != topic:
                raise ValueError(f"{path}: {panel_id} must render {topic}")
            if panel["imageMode"]["calibrationTopic"] != calibration:
                raise ValueError(f"{path}: {panel_id} must use {calibration}")

    if path.name == "drn-simulation-x500-vio.json":
        vision_topic = "/drn/sensors/vision/odometry"
        if panel_configs["RawMessages!vision"]["topicPath"] != vision_topic:
            raise ValueError(f"{path}: vision panel must render {vision_topic}")
        for plot_path in panel_configs["Plot!visionPosition"]["paths"]:
            if not plot_path["value"].startswith(f"{vision_topic}."):
                raise ValueError(f"{path}: vision plot must use {vision_topic}")
PY

if command -v pwsh >/dev/null 2>&1; then
  pwsh -NoLogo -NoProfile -File scripts/lint-powershell.ps1
else
  echo "Skipping PowerShell AST lint because pwsh is unavailable."
fi

echo "Repository lint checks passed."
