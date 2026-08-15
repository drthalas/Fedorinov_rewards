#!/usr/bin/env python3
"""CLI compatibility wrapper for the backend-owned managed-media analyzer."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.managed_media_analysis import *  # noqa: F401,F403
from backend.app.services.managed_media_analysis import main


if __name__ == "__main__":
    raise SystemExit(main())
