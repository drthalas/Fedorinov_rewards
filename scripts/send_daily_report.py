#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG = PROJECT_ROOT / ".env.daily-report"
LOG_PATH = PROJECT_ROOT / "logs" / "daily_reports.jsonl"
DEFAULT_COLORIZER_ROOT = Path.home() / "Projects" / "picture-colorizer"
DEFAULT_PDLC_ROOT = Path.home() / "Projects" / "pdlc-bot"


def _load_generate_module():
    path = PROJECT_ROOT / "scripts" / "generate_daily_report.py"
    spec = importlib.util.spec_from_file_location("generate_daily_report", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load report generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalize_argv() -> list[str]:
    return [arg.replace("–", "--", 1) if arg.startswith("–") else arg for arg in sys.argv[1:]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send safe daily Telegram report.")
    parser.add_argument("--date", dest="report_date", help="Report date in YYYY-MM-DD format. Defaults to yesterday.")
    parser.add_argument("--dry-run", action="store_true", help="Print report and recipients without sending.")
    parser.add_argument("--send-test", action="store_true", help="Send a test report to all configured recipients.")
    parser.add_argument("--send-test-to-copy-only", action="store_true", help="Send a test report only to copy recipients.")
    return parser.parse_args(_normalize_argv())


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def merged_config() -> dict[str, str]:
    config = read_env_file(LOCAL_CONFIG)
    config.update({key: value for key, value in os.environ.items() if key.startswith(("REPORT_", "COLORIZER_", "TELEGRAM_"))})
    return config


def split_ids(value: str) -> list[int]:
    ids: list[int] = []
    for item in value.replace(";", ",").split(","):
        stripped = item.strip()
        if not stripped:
            continue
        ids.append(int(stripped))
    return ids


def discover_primary_chat_id(colorizer_root: Path = DEFAULT_COLORIZER_ROOT) -> int | None:
    path = colorizer_root / "data" / "authorized_users.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    values = [int(item) for item in data.get("allowed_user_ids", [])]
    if len(values) != 1:
        return None
    return values[0]


def discover_copy_chat_ids(colorizer_root: Path = DEFAULT_COLORIZER_ROOT, pdlc_root: Path = DEFAULT_PDLC_ROOT) -> list[int]:
    ids: list[int] = []
    colorizer_env = read_env_file(colorizer_root / ".env")
    for key in ("ADMIN_USER_ID", "TELEGRAM_ADMIN_USER_ID"):
        if colorizer_env.get(key):
            ids.extend(split_ids(colorizer_env[key]))
    pdlc_env = read_env_file(pdlc_root / ".env")
    if pdlc_env.get("TELEGRAM_ALLOWED_USER_IDS"):
        ids.extend(split_ids(pdlc_env["TELEGRAM_ALLOWED_USER_IDS"]))
    deduped: list[int] = []
    seen: set[int] = set()
    for item in ids:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def resolve_token(config: dict[str, str], colorizer_root: Path = DEFAULT_COLORIZER_ROOT) -> str:
    token = config.get("COLORIZER_BOT_TOKEN") or config.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token
    colorizer_env = read_env_file(colorizer_root / ".env")
    token = colorizer_env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("Colorizer Telegram token is not configured")
    return token


def resolve_recipients(config: dict[str, str]) -> tuple[int, list[int]]:
    primary = split_ids(config.get("REPORT_PRIMARY_CHAT_ID", "")) if config.get("REPORT_PRIMARY_CHAT_ID") else []
    copy_ids = split_ids(config.get("REPORT_COPY_CHAT_IDS", "")) if config.get("REPORT_COPY_CHAT_IDS") else []
    primary_id = primary[0] if primary else discover_primary_chat_id()
    if primary_id is None:
        raise RuntimeError("Primary recipient is not configured and could not be discovered")
    if not copy_ids:
        copy_ids = discover_copy_chat_ids()
    if not copy_ids:
        raise RuntimeError("Copy recipients are not configured and could not be discovered")
    return primary_id, copy_ids


def mask_id(value: int) -> str:
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return text[:2] + "*" * (len(text) - 4) + text[-2:]


def send_message(token: str, chat_id: int, text: str) -> str:
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode()
    request = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(type(exc).__name__) from exc
    if not data.get("ok"):
        raise RuntimeError(str(data.get("description") or "Telegram send failed"))
    return str(data.get("result", {}).get("message_id", ""))


def append_log(report_date: dt.date, recipient_role: str, recipient_id: int, status: str, report_text: str, error: str = "") -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "report_date": report_date.isoformat(),
        "recipient_role": recipient_role,
        "recipient_id": recipient_id,
        "status": status,
        "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
    }
    if error:
        entry["error"] = error[:180]
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def build_report(report_date: dt.date) -> str:
    generator = _load_generate_module()
    return generator.build_report(report_date)


def main() -> int:
    args = parse_args()
    generator = _load_generate_module()
    report_date = dt.date.fromisoformat(args.report_date) if args.report_date else generator.default_report_date()
    report_text = generator.build_report(report_date)
    config = merged_config()
    primary_id, copy_ids = resolve_recipients(config)

    if args.dry_run:
        print("DRY RUN: no Telegram messages sent.")
        print(f"report_date: {report_date.isoformat()}")
        print(f"primary_recipient: {mask_id(primary_id)}")
        print("copy_recipients:", ", ".join(mask_id(item) for item in copy_ids))
        print()
        print(report_text)
        return 0

    token = resolve_token(config)
    primary_confirmed = config.get("REPORT_PRIMARY_SEND_CONFIRMED", "").lower() in {"1", "true", "yes", "y"}

    if args.send_test_to_copy_only:
        for copy_id in copy_ids:
            try:
                send_message(token, copy_id, report_text)
                append_log(report_date, "copy", copy_id, "sent_test_copy_only", report_text)
            except Exception as exc:
                append_log(report_date, "copy", copy_id, "failed", report_text, type(exc).__name__)
                raise
        return 0

    if not primary_confirmed:
        raise RuntimeError("Primary Telegram send is not confirmed. Set REPORT_PRIMARY_SEND_CONFIRMED=true only after separate approval.")

    primary_error = ""
    try:
        send_message(token, primary_id, report_text)
        append_log(report_date, "primary", primary_id, "sent_test" if args.send_test else "sent", report_text)
    except Exception as exc:
        primary_error = type(exc).__name__
        append_log(report_date, "primary", primary_id, "failed", report_text, primary_error)

    copy_text = report_text
    if primary_error:
        copy_text = f"Не удалось отправить основной отчёт Сергею: {primary_error}\n\n{report_text}"
    for copy_id in copy_ids:
        try:
            send_message(token, copy_id, copy_text)
            append_log(report_date, "copy", copy_id, "sent_test" if args.send_test else "sent", report_text)
        except Exception as exc:
            append_log(report_date, "copy", copy_id, "failed", report_text, type(exc).__name__)
            if primary_error:
                raise
    if primary_error:
        raise RuntimeError(f"Primary send failed: {primary_error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
