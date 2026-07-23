#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
import webbrowser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
PROCESS_INSPECTION_RETRY_ATTEMPTS = 3


def _machine_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _start_or_reuse_with_retry(supervisor, **kwargs):
    from backend.app.services.runtime_supervisor import RuntimeLifecycleError

    for attempt in range(PROCESS_INSPECTION_RETRY_ATTEMPTS):
        try:
            return supervisor.start_or_reuse(**kwargs)
        except RuntimeLifecycleError as exc:
            retryable = exc.category == "process-inspection-transient"
            if not retryable or attempt + 1 >= PROCESS_INSPECTION_RETRY_ATTEMPTS:
                raise
    raise AssertionError("unreachable")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fedorinov Rewards Windows runtime bootstrap.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start or reuse the single confirmed backend.")
    start.add_argument("--open-browser", action="store_true")
    start.add_argument("--wait", action="store_true")

    update = subparsers.add_parser("update", help="Apply an update outside the backend process.")
    update.add_argument("--requester-pid", type=int, required=True)
    return parser


def _start(open_browser: bool, wait: bool) -> int:
    from backend.app.config import get_settings
    from backend.app.services.runtime_identity import process_snapshot
    from backend.app.services.runtime_supervisor import RuntimeLifecycleError, RuntimeSupervisor
    from backend.app.services.updater import read_update_status
    from backend.app.version import APP_VERSION

    settings = get_settings()
    supervisor = RuntimeSupervisor()
    try:
        evidence = _start_or_reuse_with_retry(
            supervisor,
            install_root=settings.app_install_dir,
            host=settings.app_host,
            port=settings.app_port,
            expected_version=APP_VERSION,
        )
    except RuntimeLifecycleError as exc:
        print(f"Не удалось запустить приложение: {exc}", file=sys.stderr)
        return 1

    print(_machine_json(evidence.as_dict()))
    url = f"http://{settings.app_host}:{settings.app_port}"
    if open_browser:
        webbrowser.open(url)

    if not wait or evidence.reused or evidence.process is None:
        return 0

    active_token = evidence.instance_token
    try:
        exit_code = evidence.process.wait()
        if exit_code == 0:
            return 0

        deadline = time.monotonic() + 15 * 60
        success_seen_at = None
        while time.monotonic() < deadline:
            replacements = [
                inspection
                for inspection in supervisor.inspect_all()
                if inspection.confirmed
                and inspection.healthy
                and inspection.record.instance_token != active_token
                and Path(inspection.record.install_root).resolve(strict=False)
                == settings.app_install_dir.resolve(strict=False)
                and inspection.record.host == settings.app_host
                and inspection.record.port == settings.app_port
            ]
            if len(replacements) == 1:
                replacement = replacements[0].record
                active_token = replacement.instance_token
                while True:
                    snapshot = process_snapshot(replacement.pid)
                    if snapshot is None or snapshot.start_marker != replacement.process_start_marker:
                        break
                    time.sleep(0.2)
                return 0

            status = read_update_status(settings)
            if status.get("status") not in {"running", "success"}:
                return exit_code
            if status.get("status") == "success":
                success_seen_at = success_seen_at or time.monotonic()
                if time.monotonic() - success_seen_at > 7.0:
                    return exit_code
            time.sleep(0.15)
        return exit_code
    except KeyboardInterrupt:
        supervisor.stop_token(active_token)
        deadline = time.monotonic() + 2.0
        while evidence.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        return 0


def _update(requester_pid: int) -> int:
    from backend.app.config import get_settings
    from backend.app.services.supervised_update import run_supervised_update
    from backend.app.services.updater import UpdateError, write_update_status

    settings = get_settings()
    try:
        result = run_supervised_update(settings, requester_pid=requester_pid)
    except Exception as exc:
        message = str(exc) or exc.__class__.__name__
        write_update_status(settings, "error", "error", message, message)
        if isinstance(exc, UpdateError):
            print(message, file=sys.stderr)
        else:
            print(f"Не удалось завершить обновление: {message}", file=sys.stderr)
        return 1
    print(_machine_json(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    os.chdir(PROJECT_ROOT)
    if args.command == "start":
        return _start(args.open_browser, args.wait)
    return _update(args.requester_pid)


if __name__ == "__main__":
    raise SystemExit(main())
