#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TITLE = "Награды и награждённые"
FORBIDDEN_TERMS = ["GitHub Release", "ZIP", "endpoint", "router", "repository", "commit", "hash"]


def _normalize_argv() -> list[str]:
    return [arg.replace("–", "--", 1) if arg.startswith("–") else arg for arg in sys.argv[1:]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a safe Telegram release notification.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest", default="")
    parser.add_argument("--release-notes", default="")
    return parser.parse_args(_normalize_argv())


def notes_from_manifest(path: Path) -> list[str]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    notes = data.get("notes") or []
    return [str(item).strip().rstrip(".") for item in notes if str(item).strip()]


def notes_from_markdown(path: Path) -> list[str]:
    if not path.exists():
        return []
    notes: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            notes.append(stripped[2:].strip().rstrip("."))
    return notes


def sanitize_note(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" .")
    for term in FORBIDDEN_TERMS:
        text = re.sub(re.escape(term), "", text, flags=re.IGNORECASE)
    return text.strip(" .") or "В этой версии внесены улучшения и исправления"


def load_notes(version: str, manifest: Path | None = None, release_notes: Path | None = None) -> list[str]:
    notes = notes_from_manifest(manifest) if manifest else []
    if not notes:
        notes = notes_from_markdown(release_notes or PROJECT_ROOT / "release_notes" / f"{version}.md")
    if not notes:
        notes = ["В этой версии внесены улучшения и исправления"]
    return [sanitize_note(note) for note in notes[:8]]


def build_message(version: str, manifest: Path | None = None, release_notes: Path | None = None) -> str:
    notes = load_notes(version, manifest, release_notes)
    lines = [
        f"Вышла новая версия проекта “{PROJECT_TITLE}” — v{version}.",
        "",
        "Что добавлено:",
        "",
    ]
    lines.extend(f"{index}. {note}." for index, note in enumerate(notes, start=1))
    lines.extend(
        [
            "",
            "Как обновиться:",
            "",
            "1. Откройте программу.",
            "2. Перейдите в “О программе”.",
            "3. Нажмите “Проверить обновления”.",
            "4. Нажмите “Обновить”.",
            "5. Дождитесь сообщения об успешной установке.",
            "6. Закройте окно запуска и запустите start_windows.bat снова.",
            "",
            "Данные и фотографии не трогаются.",
        ]
    )
    message = "\n".join(lines)
    for term in FORBIDDEN_TERMS:
        if re.search(re.escape(term), message, re.IGNORECASE):
            raise RuntimeError(f"Forbidden technical term in release message: {term}")
    return message


def main() -> int:
    args = parse_args()
    manifest = Path(args.manifest) if args.manifest else None
    release_notes = Path(args.release_notes) if args.release_notes else None
    print(build_message(args.version, manifest, release_notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
