#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import hashlib
import importlib.util
import json
import os
import urllib.error
import urllib.parse
import urllib.request
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
    parser.add_argument("--recovery-zip", default="")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--send-test-to-copy-only", action="store_true")
    mode.add_argument("--send", action="store_true")
    parser.add_argument("--log-path", type=Path, default=LOG_PATH, help="Authoritative delivery ledger; reuse across worktrees/runs.")
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


def append_log(
    version: str,
    recipient_role: str,
    recipient_id: int,
    status: str,
    message: str,
    error: str = "",
    *,
    artifact: Path | None = None,
    message_id: str = "",
    purpose: str = "release",
    retry_safe: bool = False,
) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "version": version,
        "purpose": purpose,
        "retry_safe": retry_safe,
        "recipient_role": recipient_role,
        "recipient_id": recipient_id,
        "status": status,
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
    }
    if error:
        payload["error"] = error[:180]
    if artifact is not None:
        payload["artifact_name"] = artifact.name
        payload["artifact_size"] = artifact.stat().st_size
        payload["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if message_id:
        payload["message_id"] = str(message_id)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def build_message(version: str, manifest: str, release_notes: str, correction: bool = False) -> str:
    manifest_path = Path(manifest) if manifest else None
    notes_path = Path(release_notes) if release_notes else None
    return generator.build_message(version, manifest_path, notes_path, correction=correction)


def build_recovery_message(version: str) -> str:
    return (
        f"Сергей, это безопасное восстановление программы до версии {version}.\n\n"
        "1. Скачайте архив и нажмите «Извлечь всё».\n"
        "2. Распакуйте его в отдельную временную папку, не поверх текущей программы.\n"
        f"3. Запустите ВОССТАНОВИТЬ_И_ЗАПУСТИТЬ_{version}.bat.\n"
        "4. Проверьте показанный путь; если копий несколько, выберите папку, из которой обычно запускаете программу.\n"
        "5. Дождитесь автоматического открытия сайта.\n\n"
        "Старую папку не удаляйте. Базу и фотографии вручную не переносите. "
        "При ошибке сделайте фотографию окна и отправьте Александру."
    )


def print_dry_run(
    version: str,
    message: str,
    primary_id: int,
    copy_ids: list[int],
    recovery_zip: Path | None = None,
) -> None:
    print("DRY RUN: no Telegram messages sent.")
    print(f"version: {version}")
    print(f"primary_recipient: {daily.mask_id(primary_id)}")
    print("copy_recipients:", ", ".join(daily.mask_id(item) for item in copy_ids))
    if recovery_zip is not None:
        print(f"recovery_zip: {recovery_zip}")
        print(f"recovery_size: {recovery_zip.stat().st_size}")
        print(f"recovery_sha256: {hashlib.sha256(recovery_zip.read_bytes()).hexdigest()}")
    print()
    print(message)


class DeliveryRejected(RuntimeError):
    """Telegram explicitly rejected the request; retry cannot duplicate it."""


def send_notification(token: str, recipient_id: int, message: str, artifact: Path | None) -> str:
    if artifact is not None:
        # The shared document sender hides API error details. Treat any exception
        # conservatively as uncertain; never infer rejection from exception text.
        return daily.send_document(token, recipient_id, artifact, message)
    body = urllib.parse.urlencode({
        "chat_id": recipient_id, "text": message, "disable_web_page_preview": "true",
    }).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # HTTP/server/proxy errors alone do not prove non-delivery.
        try:
            data = json.loads(exc.read().decode("utf-8"))
        except (ValueError, OSError):
            raise RuntimeError("Uncertain Telegram response") from None
        finally:
            exc.close()
        if data.get("ok") is False and 400 <= data.get("error_code", 0) < 500 and exc.code < 500:
            raise DeliveryRejected("Telegram rejected request") from None
        raise RuntimeError("Uncertain Telegram response") from None
    if data.get("ok") is False and 400 <= data.get("error_code", 0) < 500:
        raise DeliveryRejected("Telegram rejected request")
    result = data.get("result", {})
    message_id = result.get("message_id")
    if (data.get("ok") is not True or type(message_id) is not int or message_id <= 0
            or result.get("chat", {}).get("id") != recipient_id):
        raise RuntimeError("Uncertain Telegram acknowledgement")
    return str(message_id)


def preflight(config: dict[str, str]) -> tuple[int, list[int]]:
    # Release roles must be explicit; unrelated app discovery cannot identify Owner.
    try:
        primary = daily.split_ids(config.get("REPORT_PRIMARY_CHAT_ID", ""))
        copies = daily.split_ids(config.get("REPORT_COPY_CHAT_IDS", ""))
    except ValueError:
        raise RuntimeError("Preflight FAIL: invalid recipient configuration") from None
    if len(primary) != 1 or len(copies) != 1 or not all(primary + copies) or primary[0] == copies[0]:
        raise RuntimeError("Preflight FAIL: configure distinct Sergey primary and exactly one Owner copy")
    return primary[0], copies


@contextmanager
def ledger_lock():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = LOG_PATH.with_name(LOG_PATH.name + ".lock")
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError("Delivery ledger locked: STOP; inspect pending attempt before retry") from None
    try:
        yield
    finally:
        lock.rmdir()


def delivery_state(version: str, recipient_id: int, purpose: str) -> tuple[str, str]:
    state, message_id = "pending", ""
    if not LOG_PATH.exists():
        return state, message_id
    for line in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            entry_version = str(entry["version"]).removeprefix("v")
            entry_recipient = int(entry["recipient_id"])
            status = entry["status"]
        except (ValueError, TypeError, KeyError):
            raise RuntimeError("Delivery ledger invalid: STOP, do not resend") from None
        if entry_recipient != recipient_id:
            continue
        entry_purpose = entry.get("purpose", "release")
        if purpose != entry_purpose or (purpose == "release" and entry_version != version):
            continue
        # Historical test copies never establish release delivery.
        if status == "sent_test_copy_only":
            continue
        if status == "sent" and str(entry.get("message_id", "")).isdigit() and int(entry["message_id"]) > 0:
            state, message_id = "sent", str(entry["message_id"])
        elif state != "sent":
            # Legacy 'failed', missing ID, interrupted attempt and all unknown
            # statuses require an Owner decision, not an automatic retry.
            state = "failed" if status == "failed" and entry.get("retry_safe") is True else "uncertain"
    return state, message_id


def deliver(version: str, recipients: list[tuple[str, int]], message: str,
            token: str, artifact: Path | None = None, purpose: str = "release") -> int:
    with ledger_lock():
        states = {rid: delivery_state(version, rid, purpose) for _, rid in recipients}
        if any(status == "uncertain" for status, _ in states.values()):
            for role, rid in recipients:
                status, mid = states[rid]
                print(f"{role}: {status}; recipient={daily.mask_id(rid)}; message_id={mid or '-'}")
            print("Telegram FAIL: uncertain delivery; STOP for Owner decision")
            return 2
        for role, rid in recipients:
            status, mid = states[rid]
            if status != "sent":
                # Persist intent before touching network. A crash leaves an
                # uncertain attempt and prevents blind retries on the next run.
                append_log(version, role, rid, "attempt_started", message, purpose=purpose)
                try:
                    mid = send_notification(token, rid, message, artifact)
                    if not str(mid).isdigit() or int(mid) <= 0:
                        raise RuntimeError("Missing message ID")
                except DeliveryRejected:
                    status, mid = "failed", ""
                    append_log(version, role, rid, status, message, "DeliveryRejected",
                               purpose=purpose, retry_safe=True)
                except Exception as exc:
                    status, mid = "uncertain", ""
                    append_log(version, role, rid, status, message, type(exc).__name__, purpose=purpose)
                else:
                    status = "sent"
                    append_log(version, role, rid, status, message, artifact=artifact,
                               message_id=mid, purpose=purpose)
            states[rid] = status, mid
            if status == "uncertain":
                # Do not continue sending after an ambiguous API response.
                break
        for role, rid in recipients:
            status, mid = states[rid]
            print(f"{role}: {status}; recipient={daily.mask_id(rid)}; message_id={mid or '-'}")
        statuses = [status for status, _ in states.values()]
        if all(status == "sent" for status in statuses):
            print("Telegram PASS: independent API acknowledgements" if purpose == "release"
                  else "Identity test API PASS; STOP until Owner confirms receipt")
            return 0
        print("Telegram partial FAIL" if "sent" in statuses else "Telegram FAIL")
        return 2 if "uncertain" in statuses else 1


def main() -> int:
    global LOG_PATH
    args = parse_args()
    LOG_PATH = args.log_path.resolve()
    version = args.version.removeprefix("v")
    config = daily.merged_config()
    primary_id, copy_ids = preflight(config)
    recovery_zip = Path(args.recovery_zip).resolve(strict=False) if args.recovery_zip else None
    if args.send_test_to_copy_only:
        if recovery_zip or args.correction or args.manifest or args.release_notes:
            raise RuntimeError("Identity test accepts no release content or artifacts")
        message = ("Нейтральная проверка связи ALE-502. "
                   "Если это ваш чат, подтвердите Александру получение словами «пришло». "
                   "Это тестовое сообщение; никаких действий с программой не требуется.")
    elif recovery_zip is not None:
        if not recovery_zip.is_file():
            raise FileNotFoundError(recovery_zip)
        expected_name = f"FedorinovRewards_Recovery_v{version}.zip"
        if recovery_zip.name != expected_name:
            raise RuntimeError(f"Recovery artifact must be named {expected_name}.")
        message = build_recovery_message(version)
    else:
        message = build_message(version, args.manifest, args.release_notes, correction=args.correction)

    if args.dry_run or not args.send and not args.send_test_to_copy_only:
        print_dry_run(version, message, primary_id, copy_ids, recovery_zip)
        return 0

    token = daily.resolve_token(config)
    if args.send_test_to_copy_only:
        return deliver(version, [("Owner", copy_ids[0])], message, token, purpose="owner_identity_test")
    if config.get("REPORT_PRIMARY_SEND_CONFIRMED", "").lower() not in {"1", "true", "yes", "y"}:
        raise RuntimeError("Primary Telegram send is not confirmed.")
    return deliver(version, [("Sergey", primary_id), ("Owner", copy_ids[0])], message, token, recovery_zip)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Never print API URLs, config values, exception text or private IDs.
        print(f"Telegram FAIL: {type(exc).__name__}; inspect preflight/ledger locally", file=sys.stderr)
        raise SystemExit(1)
