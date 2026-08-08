#!/usr/bin/env bash
set -Eeuo pipefail

runtime_dir="$(mktemp -d)"
trap 'rm -rf -- "${runtime_dir}"' EXIT
export XDG_RUNTIME_DIR="${runtime_dir}"

if ! renderer_info="$(EGL_PLATFORM=surfaceless eglinfo -B 2>&1)"; then
  echo "Gazebo GPU rendering is unavailable: EGL could not initialize." >&2
  exit 1
fi

if grep -Eiq 'llvmpipe|softpipe|swrast|software rasterizer' <<<"${renderer_info}"; then
  echo "Gazebo GPU rendering is unavailable: EGL selected a software renderer." >&2
  exit 1
fi

if ! grep -Eiq 'EGL vendor string:|OpenGL( core profile)? renderer string:|Device:' \
  <<<"${renderer_info}"; then
  echo "Gazebo GPU rendering is unavailable: EGL did not report a renderer." >&2
  exit 1
fi

grep -Ei 'EGL vendor string:|OpenGL( core profile)? renderer string:|Device:' \
  <<<"${renderer_info}" | head -n 3
