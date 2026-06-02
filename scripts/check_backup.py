#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile
import sys


REQUIRED_ROOT_ITEMS = [
    "database/MyDatabase.sqlite",
    "Source/",
    "SourceMark/",
    "default/",
]


def _has_item(names: set[str], item: str) -> bool:
    candidates = [item, f"Rewards/{item}"]
    if item.endswith("/"):
        return any(name.startswith(candidate) for candidate in candidates for name in names)
    return any(candidate in names for candidate in candidates)


def check_backup(path: Path) -> tuple[bool, list[str], int]:
    missing: list[str] = []
    with ZipFile(path) as archive:
        bad_file = archive.testzip()
        if bad_file:
            missing.append(f"corrupt zip member: {bad_file}")
        names = set(archive.namelist())
        for item in REQUIRED_ROOT_ITEMS:
            if not _has_item(names, item):
                missing.append(item)
        return not missing, missing, len(names)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 scripts/check_backup.py <backup.zip>", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser().resolve()
    if not path.exists() or not path.is_file():
        print(f"backup file does not exist: {path}", file=sys.stderr)
        return 1
    try:
        ok, missing, member_count = check_backup(path)
    except BadZipFile as exc:
        print(f"backup is not a readable zip: {exc}", file=sys.stderr)
        return 1

    print(f"path: {path}")
    print(f"members: {member_count}")
    print(f"readable_zip: {str(ok).lower()}")
    if missing:
        print("missing:")
        for item in missing:
            print(f"- {item}")
        return 1
    print("required_items: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
