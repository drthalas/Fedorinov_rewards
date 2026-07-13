#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from shutil import copy2, copytree, rmtree
from zipfile import ZIP_DEFLATED, ZipFile
import base64
import fnmatch
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.update_archive_policy import SYSTEM_UI_ASSET_PATHS  # noqa: E402


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
EMBEDDED_UI_ASSETS = {Path(*parts) for parts in SYSTEM_UI_ASSET_PATHS}

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
    Path("scripts") / "generate_release_telegram_message.py",
    Path("scripts") / "send_release_notification.py",
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


def _asset_variable(relative: Path) -> str:
    return "--fr-asset-" + "-".join(relative.with_suffix("").parts[4:])


def _asset_web_path(relative: Path) -> str:
    return "/static/" + "/".join(relative.parts[3:])


def _asset_mime_type(relative: Path) -> str:
    suffix = relative.suffix.casefold()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    raise ValueError(f"unsupported embedded UI asset type: {relative}")


def _embed_ui_assets() -> None:
    styles_path = PACKAGE_ROOT / "backend/app/static/styles.css"
    styles = styles_path.read_text(encoding="utf-8")
    declarations: list[str] = []
    for relative in sorted(EMBEDDED_UI_ASSETS):
        source = PROJECT_ROOT / relative
        web_path = _asset_web_path(relative)
        variable = _asset_variable(relative)
        marker = f'url("{web_path}")'
        if marker not in styles:
            raise RuntimeError(f"UI asset is not referenced by packaged CSS: {relative}")
        encoded = base64.b64encode(source.read_bytes()).decode("ascii")
        declarations.append(f'  {variable}: url("data:{_asset_mime_type(relative)};base64,{encoded}");')
        styles = styles.replace(marker, f"var({variable})")
    styles_path.write_text(":root {\n" + "\n".join(declarations) + "\n}\n" + styles, encoding="utf-8")


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
    _embed_ui_assets()
    file_count = _make_zip()
    size = ZIP_PATH.stat().st_size

    print(f"folder: {PACKAGE_ROOT}")
    print(f"zip: {ZIP_PATH}")
    print(f"size_bytes: {size}")
    print(f"files: {file_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
