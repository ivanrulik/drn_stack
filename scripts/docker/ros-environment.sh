#!/usr/bin/env bash
set -Eeo pipefail

source /opt/ros/humble/setup.bash
source /opt/drn_ws/install/setup.bash

if [[ -n "${DRN_PROJECT_SETUP:-}" ]]; then
  case "${DRN_PROJECT_SETUP}" in
    /opt/drn_project_ws/install/setup.bash) ;;
    *)
      echo "DRN_PROJECT_SETUP must be /opt/drn_project_ws/install/setup.bash." >&2
      return 2
      ;;
  esac
  if [[ ! -f "${DRN_PROJECT_SETUP}" ]]; then
    echo "Project overlay setup file was not found: ${DRN_PROJECT_SETUP}" >&2
    return 1
  fi
  # shellcheck source=/opt/drn_project_ws/install/setup.bash
  source "${DRN_PROJECT_SETUP}"
fi
