#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.version import APP_NAME, APP_VERSION  # noqa: E402


def main() -> int:
    print(f"{APP_NAME} {APP_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
