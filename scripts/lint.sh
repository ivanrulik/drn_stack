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
yaml_files+=(compose.yaml .yamllint.yml)
yamllint --strict "${yaml_files[@]}"

docker compose --project-name drn-stack --file compose.yaml config --quiet

python3 -m compileall -q drn_viz/launch
python3 - <<'PY'
import json
from pathlib import Path
from xml.etree import ElementTree

for path in (
    Path("drn_control/package.xml"),
    Path("drn_viz/package.xml"),
    *Path("drn_viz/urdf").glob("*.urdf"),
):
    ElementTree.parse(path)

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
PY

if command -v pwsh >/dev/null 2>&1; then
  pwsh -NoLogo -NoProfile -File scripts/lint-powershell.ps1
else
  echo "Skipping PowerShell AST lint because pwsh is unavailable."
fi

echo "Repository lint checks passed."
