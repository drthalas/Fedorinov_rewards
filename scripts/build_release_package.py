#!/usr/bin/env python3
from __future__ import annotations

from datetime import date
import argparse
import hashlib
import json
from pathlib import Path
from shutil import rmtree
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = PROJECT_ROOT / "dist"
RELEASE_NOTES_ROOT = PROJECT_ROOT / "release_notes"
REPOSITORY_SLUG = "drthalas/Fedorinov_rewards"
PACKAGE_BASENAME = "FedorinovRewards_WebPreview"
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.version import APP_VERSION  # noqa: E402
from scripts import build_windows_preview_package  # noqa: E402


def versioned_zip_name(version: str = APP_VERSION) -> str:
    return f"{PACKAGE_BASENAME}_v{version}.zip"


def versioned_zip_path(version: str = APP_VERSION) -> Path:
    return DIST_ROOT / versioned_zip_name(version)


def latest_json_path() -> Path:
    return DIST_ROOT / "latest.json"


def release_notes_path(version: str = APP_VERSION) -> Path:
    return RELEASE_NOTES_ROOT / f"{version}.md"


def download_url(version: str = APP_VERSION) -> str:
    return f"https://github.com/{REPOSITORY_SLUG}/releases/download/v{version}/{versioned_zip_name(version)}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_notes(version: str = APP_VERSION) -> list[str]:
    path = release_notes_path(version)
    if not path.exists():
        return []
    notes: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            notes.append(stripped[2:].rstrip("."))
    return notes


def build_release_package(version: str = APP_VERSION) -> dict[str, object]:
    if version != APP_VERSION:
        raise ValueError(f"requested version {version} does not match APP_VERSION {APP_VERSION}")
    if DIST_ROOT.exists():
        rmtree(DIST_ROOT)
    DIST_ROOT.mkdir(parents=True, exist_ok=True)

    build_windows_preview_package.main()
    source_zip = build_windows_preview_package.ZIP_PATH
    target_zip = versioned_zip_path(version)
    source_zip.replace(target_zip)

    checksum = sha256_file(target_zip)
    manifest = {
        "version": version,
        "released_at": date.today().isoformat(),
        "download_url": download_url(version),
        "sha256": checksum,
        "notes": release_notes(version),
    }
    manifest_path = latest_json_path()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "version": version,
        "zip_path": str(target_zip),
        "latest_json_path": str(manifest_path),
        "sha256": checksum,
        "download_url": manifest["download_url"],
        "notes_count": len(manifest["notes"]),
        "size_bytes": target_zip.stat().st_size,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build versioned release ZIP and latest.json assets.")
    parser.add_argument("--version", default=APP_VERSION, help="Release version. Must match backend.app.version.APP_VERSION.")
    args = parser.parse_args(argv)
    try:
        result = build_release_package(args.version)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
