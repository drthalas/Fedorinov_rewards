#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXTERNAL_DIR="${ROOT_DIR}/legacy/_external"

mkdir -p "${EXTERNAL_DIR}"

clone_or_update() {
  local repo_url="$1"
  local target_dir="$2"

  if [ -d "${target_dir}/.git" ]; then
    git -C "${target_dir}" fetch --all --prune
  else
    git clone "${repo_url}" "${target_dir}"
  fi
}

clone_or_update "https://github.com/erypalovyury/rewards" "${EXTERNAL_DIR}/rewards"
clone_or_update "https://github.com/erypalovyury/activation-rewards" "${EXTERNAL_DIR}/activation-rewards"

echo "Legacy sources are available under ${EXTERNAL_DIR}"
