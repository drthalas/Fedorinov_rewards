#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [ -f ".env" ]; then
  while IFS='=' read -r key value; do
    case "${key}" in
      ""|\#*) continue ;;
    esac
    if [ -z "${!key+x}" ]; then
      export "${key}=${value}"
    fi
  done < ".env"
fi

APP_HOST="${APP_HOST:-127.0.0.1}"
APP_PORT="${APP_PORT:-8080}"

if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  PYTHON_BIN="python"
fi

"${PYTHON_BIN}" -m uvicorn backend.app.main:app --host "${APP_HOST}" --port "${APP_PORT}"
