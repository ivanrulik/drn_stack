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
from pathlib import Path
from xml.etree import ElementTree

for path in (Path("drn_viz/package.xml"), *Path("drn_viz/urdf").glob("*.urdf")):
    ElementTree.parse(path)
PY

if command -v pwsh >/dev/null 2>&1; then
  pwsh -NoLogo -NoProfile -File scripts/lint-powershell.ps1
else
  echo "Skipping PowerShell AST lint because pwsh is unavailable."
fi

echo "Repository lint checks passed."
