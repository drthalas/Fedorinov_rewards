#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile, ZipFile
import fnmatch
import sys


FORBIDDEN_EXACT_NAMES = {
    ".env",
    ".venv",
}
FORBIDDEN_DIR_PARTS = {
    ".venv",
    "database",
    "Source",
    "SourceMark",
    "backups",
    "updates",
}
FORBIDDEN_PATH_PREFIXES = [
    ("legacy", "_external"),
    ("docs", "reports"),
]
FORBIDDEN_PATTERNS = [
    "*.sqlite",
    "*.db",
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.pdf",
    "*.exe",
    "*.dll",
    "*.zip",
]


def _normalize_member(path: str) -> tuple[str, ...]:
    return tuple(part for part in Path(path).parts if part not in ("", "."))


def _strip_package_root(parts: tuple[str, ...]) -> tuple[str, ...]:
    if parts and parts[0] == "FedorinovRewards_WebPreview":
        return parts[1:]
    return parts


def _is_forbidden(path: str) -> str | None:
    raw_parts = _normalize_member(path)
    parts = _strip_package_root(raw_parts)
    if not parts:
        return None

    name = parts[-1]
    if name in FORBIDDEN_EXACT_NAMES:
        return f"forbidden exact file name: {name}"
    if any(part in FORBIDDEN_DIR_PARTS for part in parts):
        return "forbidden directory path"
    for prefix in FORBIDDEN_PATH_PREFIXES:
        if len(parts) >= len(prefix) and parts[: len(prefix)] == prefix:
            return f"forbidden path prefix: {'/'.join(prefix)}"
    for pattern in FORBIDDEN_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return f"forbidden pattern: {pattern}"
    return None


def _iter_folder_members(path: Path):
    for member in path.rglob("*"):
        if member.is_file():
            yield str(member.relative_to(path))


def _iter_zip_members(path: Path):
    with ZipFile(path) as archive:
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
