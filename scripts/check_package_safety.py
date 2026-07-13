#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.update_archive_policy import (  # noqa: E402
    ArchivePolicyError,
    forbidden_relative_reason,
    normalize_archive_path,
    strip_package_root,
    validate_zip_members,
)


def _normalize_member(path: str) -> tuple[str, ...]:
    try:
        return normalize_archive_path(path)
    except ArchivePolicyError:
        return ()


def _strip_package_root(parts: tuple[str, ...]) -> tuple[str, ...]:
    return strip_package_root(parts)


def _is_forbidden(path: str) -> str | None:
    return forbidden_relative_reason(path)


def _iter_folder_members(path: Path):
    for member in path.rglob("*"):
        if member.is_file():
            yield str(member.relative_to(path))


def _iter_zip_members(path: Path):
    with ZipFile(path) as archive:
        validate_zip_members(archive)
        bad_file = archive.testzip()
        if bad_file:
            raise RuntimeError(f"zip has corrupt member: {bad_file}")
        yield from archive.namelist()


def check_package(path: Path) -> tuple[bool, list[str], int]:
    if path.is_dir():
        members = list(_iter_folder_members(path))
    else:
        members = list(_iter_zip_members(path))

    violations: list[str] = []
    for member in members:
        reason = _is_forbidden(member)
        if reason:
            violations.append(f"{member}: {reason}")
    return not violations, violations, len(members)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 scripts/check_package_safety.py <package-folder-or-zip>", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser().resolve()
    if not path.exists():
        print(f"package does not exist: {path}", file=sys.stderr)
        return 1
    try:
        ok, violations, member_count = check_package(path)
    except BadZipFile as exc:
        print(f"package is not a readable zip: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"package safety check failed: {exc}", file=sys.stderr)
        return 1
    except ArchivePolicyError as exc:
        print(f"package safety check failed: {exc}", file=sys.stderr)
        return 1

    print(f"path: {path}")
    print(f"members: {member_count}")
    print(f"safe: {str(ok).lower()}")
    if violations:
        print("violations:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("forbidden_content: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
