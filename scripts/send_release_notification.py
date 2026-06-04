#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = PROJECT_ROOT / "logs" / "release_notifications.jsonl"


def _normalize_argv() -> list[str]:
    return [arg.replace("–", "--", 1) if arg.startswith("–") else arg for arg in sys.argv[1:]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send Telegram notification about a new release.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest", default="")
    parser.add_argument("--release-notes", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--send-test-to-copy-only", action="store_true")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--correction", action="store_true")
    return parser.parse_args(_normalize_argv())


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


daily = load_module("daily_report_sender", PROJECT_ROOT / "scripts" / "send_daily_report.py")
generator = load_module("release_message_generator", PROJECT_ROOT / "scripts" / "generate_release_telegram_message.py")


def append_log(version: str, recipient_role: str, recipient_id: int, status: str, message: str, error: str = "") -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "version": version,
        "recipient_role": recipient_role,
        "recipient_id": recipient_id,
        "status": status,
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }
    if error:
        payload["error"] = error[:180]
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def build_message(version: str, manifest: str, release_notes: str, correction: bool = False) -> str:
    manifest_path = Path(manifest) if manifest else None
    notes_path = Path(release_notes) if release_notes else None
    return generator.build_message(version, manifest_path, notes_path, correction=correction)


def print_dry_run(version: str, message: str, primary_id: int, copy_ids: list[int]) -> None:
    print("DRY RUN: no Telegram messages sent.")
    print(f"version: {version}")
    print(f"primary_recipient: {daily.mask_id(primary_id)}")
    print("copy_recipients:", ", ".join(daily.mask_id(item) for item in copy_ids))
    print()
    print(message)


def main() -> int:
    args = parse_args()
    config = daily.merged_config()
    primary_id, copy_ids = daily.resolve_recipients(config)
    message = build_message(args.version, args.manifest, args.release_notes, correction=args.correction)

    if args.dry_run or not args.send and not args.send_test_to_copy_only:
        print_dry_run(args.version, message, primary_id, copy_ids)
        return 0

    token = daily.resolve_token(config)
    if args.send_test_to_copy_only:
        for copy_id in copy_ids:
            try:
                daily.send_message(token, copy_id, message)
                append_log(args.version, "copy", copy_id, "sent_test_copy_only", message)
            except Exception as exc:
                append_log(args.version, "copy", copy_id, "failed", message, type(exc).__name__)
                raise
        return 0

    if args.send:
        primary_confirmed = config.get("REPORT_PRIMARY_SEND_CONFIRMED", "").lower() in {"1", "true", "yes", "y"}
        if not primary_confirmed:
            raise RuntimeError("Primary Telegram send is not confirmed.")
        primary_error = ""
        try:
            daily.send_message(token, primary_id, message)
            append_log(args.version, "primary", primary_id, "sent", message)
        except Exception as exc:
            primary_error = type(exc).__name__
            append_log(args.version, "primary", primary_id, "failed", message, primary_error)
        copy_message = message
        if primary_error:
            copy_message = f"Не удалось отправить уведомление Сергею: {primary_error}\n\n{message}"
        for copy_id in copy_ids:
            try:
                daily.send_message(token, copy_id, copy_message)
                append_log(args.version, "copy", copy_id, "sent", message)
            except Exception as exc:
                append_log(args.version, "copy", copy_id, "failed", message, type(exc).__name__)
                if primary_error:
                    raise
        if primary_error:
            raise RuntimeError(f"Primary send failed: {primary_error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
