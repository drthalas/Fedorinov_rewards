#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.version import APP_NAME, APP_VERSION  # noqa: E402
from scripts.build_recovery_package import recovery_zip_path  # noqa: E402
from scripts.build_release_package import latest_json_path, release_notes_path, versioned_zip_path  # noqa: E402


def release_tag(version: str = APP_VERSION) -> str:
    return f"v{version}"


def release_title(version: str = APP_VERSION) -> str:
    return f"{APP_NAME} v{version}"


def release_assets(version: str = APP_VERSION) -> list[Path]:
    assets = [versioned_zip_path(version)]
    if version == "2.0.6":
        assets.append(recovery_zip_path(version))
    assets.append(latest_json_path())
    return assets


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["gh", *args], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)


def check_gh_ready() -> tuple[bool, list[str]]:
    messages: list[str] = []
    if shutil.which("gh") is None:
        return False, ["gh CLI is not installed. Install GitHub CLI and authenticate locally."]

    version_result = _run_gh(["--version"])
    if version_result.returncode != 0:
        messages.append("gh --version failed.")
        return False, messages
    messages.append(version_result.stdout.splitlines()[0] if version_result.stdout else "gh CLI found.")

    auth_result = _run_gh(["auth", "status"])
    if auth_result.returncode != 0:
        messages.append("gh auth status failed. Run `gh auth login` locally; do not paste tokens into project files.")
        return False, messages
    messages.append("gh auth status: authenticated")
    return True, messages


def _validate_assets(version: str) -> list[Path]:
    assets = release_assets(version)
    missing = [path for path in assets if not path.exists()]
    if missing:
        names = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"release assets are missing: {names}")
    return assets


def publish_release(version: str = APP_VERSION, dry_run: bool = False) -> int:
    tag = release_tag(version)
    title = release_title(version)
    notes_path = release_notes_path(version)
    assets = _validate_assets(version)

    print(f"tag: {tag}")
    print(f"title: {title}")
    print(f"notes_path: {notes_path}")
    print("assets:")
    for asset in assets:
        print(f"- {asset}")

    if dry_run:
        print("dry_run: true")
        print("release_created: false")
        return 0

    ready, messages = check_gh_ready()
    for message in messages:
        print(message)
    if not ready:
        return 1

    existing = _run_gh(["release", "view", tag])
    if existing.returncode == 0:
        print(f"release already exists: {tag}")
        print("Refusing to overwrite. Delete/update it manually or add a future explicit replace flow.")
        return 1

    command = [
        "release",
        "create",
        tag,
        "--title",
        title,
        "--notes-file",
        str(notes_path),
        *[str(asset) for asset in assets],
    ]
    result = _run_gh(command)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish the GitHub Release assets for the current app version.")
    parser.add_argument("--dry-run", action="store_true", help="Print release metadata without calling GitHub.")
    args = parser.parse_args(argv)
    try:
        return publish_release(dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
