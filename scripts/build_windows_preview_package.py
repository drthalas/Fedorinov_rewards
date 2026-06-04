#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from shutil import copy2, copytree, rmtree
from zipfile import ZIP_DEFLATED, ZipFile
import fnmatch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = PROJECT_ROOT / "dist"
PACKAGE_NAME = "FedorinovRewards_WebPreview"
PACKAGE_ROOT = DIST_ROOT / PACKAGE_NAME
ZIP_PATH = DIST_ROOT / "FedorinovRewards_WebPreview_v0.1.zip"

EXCLUDED_NAMES = {
    ".git",
    ".env",
    ".venv",
    "data",
    "database",
    "Source",
    "SourceMark",
    "backups",
    "dist",
    "updates",
    "__pycache__",
}
EXCLUDED_PATHS = {
    Path("legacy") / "_external",
    Path("docs") / "reports",
}
EXCLUDED_PATTERNS = [
    "*.sqlite",
    "*.db",
    "*.zip",
    "*.jpg",
    "*.jpeg",
    "*.png",
    "*.pdf",
    "*.exe",
    "*.dll",
]

DIRECTORIES_TO_COPY = [
    "backend",
]
FILES_TO_COPY = [
    Path("scripts") / "inspect_local_data.py",
    Path("scripts") / "check_media_links.py",
    Path("scripts") / "backup_dev_data.py",
    Path("scripts") / "check_backup.py",
    Path("scripts") / "check_update.py",
    Path("scripts") / "apply_update.py",
    Path("HELP_RU.md"),
    Path("README.md"),
    Path("docs") / "WINDOWS_PREVIEW_RUNBOOK.md",
    Path("docs") / "WINDOWS_OWNER_CHECKLIST.md",
    Path("docs") / "UPDATE_SYSTEM_PLAN.md",
    Path("docs") / "update_manifest.example.json",
    Path("start_windows.bat"),
    Path("start_windows.ps1"),
    Path(".env.windows.example"),
]


def _is_excluded(path: Path) -> bool:
    relative = path.relative_to(PROJECT_ROOT)
    if any(relative == excluded or relative.is_relative_to(excluded) for excluded in EXCLUDED_PATHS):
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in EXCLUDED_PATTERNS)


def _ignore_copytree(directory: str, names: list[str]) -> set[str]:
    source_dir = Path(directory)
    ignored: set[str] = set()
    for name in names:
        candidate = source_dir / name
        try:
            project_candidate = candidate.resolve()
            if project_candidate.is_relative_to(PROJECT_ROOT) and _is_excluded(project_candidate):
                ignored.add(name)
        except FileNotFoundError:
            ignored.add(name)
    return ignored


def _copy_required_files() -> None:
    for directory in DIRECTORIES_TO_COPY:
        source = PROJECT_ROOT / directory
        destination = PACKAGE_ROOT / directory
        copytree(source, destination, ignore=_ignore_copytree)

    for relative in FILES_TO_COPY:
        source = PROJECT_ROOT / relative
        destination = PACKAGE_ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        copy2(source, destination)


def _make_zip() -> int:
    file_count = 0
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with ZipFile(ZIP_PATH, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE_ROOT.rglob("*")):
            if path.is_file():
                archive.write(path, Path(PACKAGE_NAME) / path.relative_to(PACKAGE_ROOT))
                file_count += 1
    return file_count


def main() -> int:
    if PACKAGE_ROOT.exists():
        rmtree(PACKAGE_ROOT)
    PACKAGE_ROOT.mkdir(parents=True)

    _copy_required_files()
    file_count = _make_zip()
    size = ZIP_PATH.stat().st_size

    print(f"folder: {PACKAGE_ROOT}")
    print(f"zip: {ZIP_PATH}")
    print(f"size_bytes: {size}")
    print(f"files: {file_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
