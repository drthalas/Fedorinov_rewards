#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import get_settings  # noqa: E402
from backend.app.services.runtime_supervisor import RuntimeSupervisor  # noqa: E402
from backend.app.services.supervised_update import schedule_supervised_update  # noqa: E402
from backend.app.services.updater import UpdateError, apply_update  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or apply a GitHub Release update.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Build an update plan without changing files.")
    mode.add_argument("--apply", action="store_true", help="Apply the update. This changes application files.")
    args = parser.parse_args(argv)
    settings = get_settings()
    try:
        if not args.apply:
            result = apply_update(settings, dry_run=True)
        else:
            matching = [
                inspection
                for inspection in RuntimeSupervisor().inspect_all()
                if inspection.confirmed
                and inspection.healthy
                and Path(inspection.record.install_root).resolve(strict=False)
                == settings.app_install_dir.resolve(strict=False)
                and inspection.record.host == settings.app_host
                and inspection.record.port == settings.app_port
            ]
            if len(matching) != 1:
                raise UpdateError("Не найден ровно один подтверждённый backend для обновления.")
            result = schedule_supervised_update(settings, requester_pid=matching[0].record.pid)
    except UpdateError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
