#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from typing import Any, List, Optional
from urllib.request import Request, urlopen
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MANIFEST_URL = (
    "https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json"
)
DEFAULT_CHANNEL_ROOT = (
    Path.home() / "Library" / "Application Support" / "FedorinovRewards" / "owner-candidate-channel"
)
DEFAULT_BASE_URL = "http://Mac-mini-hermes.local:18387"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def fetch_json(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"},
    )
    with urlopen(request, timeout=20) as response:
        value = json.loads(response.read().decode("utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object from {url}")
    return value


def parse_version_text(text: str) -> str:
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise ValueError("APP_VERSION is missing")
    return match.group(1)


def package_version(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        matches = [
            name
            for name in archive.namelist()
            if PurePosixPath(name).parts[-3:] == ("backend", "app", "version.py")
        ]
        if len(matches) != 1:
            raise ValueError("candidate ZIP must contain exactly one backend/app/version.py")
        return parse_version_text(archive.read(matches[0]).decode("utf-8"))


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
        with source.open("rb") as input_file:
            shutil.copyfileobj(input_file, handle, length=1024 * 1024)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(temporary, 0o640)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(destination: Path, value: dict[str, Any]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(temporary, 0o640)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def validate_candidate(
    *,
    artifact: Path,
    source_manifest: Path,
    expected_commit: str,
    expected_version: str,
    expected_sha256: str,
    expected_size: int,
    expected_public_version: str,
    production_manifest: dict[str, Any],
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("expected candidate commit must be a full lowercase SHA")
    git("cat-file", "-e", f"{expected_commit}^{{commit}}")
    committed_version = parse_version_text(
        git("show", f"{expected_commit}:backend/app/version.py")
    )
    if committed_version != expected_version:
        raise ValueError(
            f"candidate commit version mismatch: expected {expected_version}, got {committed_version}"
        )

    artifact = artifact.resolve(strict=True)
    if artifact.name != f"FedorinovRewards_WebPreview_v{expected_version}.zip":
        raise ValueError("candidate artifact filename does not match expected version")
    if artifact.stat().st_size != expected_size:
        raise ValueError("candidate artifact size does not match expected size")
    artifact_sha = sha256_file(artifact)
    if artifact_sha != expected_sha256:
        raise ValueError("candidate artifact SHA256 does not match expected SHA256")
    if package_version(artifact) != expected_version:
        raise ValueError("candidate package version does not match expected version")

    source = load_json(source_manifest.resolve(strict=True))
    if str(source.get("version")) != expected_version:
        raise ValueError("source manifest version does not match expected version")
    if str(source.get("sha256")) != expected_sha256:
        raise ValueError("source manifest SHA256 does not match expected SHA256")
    if str(production_manifest.get("version")) != expected_public_version:
        raise ValueError("production channel version changed")
    if expected_public_version == expected_version:
        raise ValueError("candidate version must differ from production")

    return {
        "version": expected_version,
        "released_at": source.get("released_at"),
        "notes": source.get("notes") if isinstance(source.get("notes"), list) else [],
        "filename": artifact.name,
        "size": expected_size,
        "sha256": artifact_sha,
        "candidate_commit": expected_commit,
        "production_version_at_publish": expected_public_version,
    }


def publish(
    *,
    artifact: Path,
    source_manifest: Path,
    channel_root: Path,
    base_url: str,
    expected_commit: str,
    expected_version: str,
    expected_sha256: str,
    expected_size: int,
    expected_public_version: str,
    production_manifest: dict[str, Any],
) -> dict[str, Any]:
    metadata = validate_candidate(
        artifact=artifact,
        source_manifest=source_manifest,
        expected_commit=expected_commit,
        expected_version=expected_version,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
        expected_public_version=expected_public_version,
        production_manifest=production_manifest,
    )
    base_url = base_url.rstrip("/")
    if not re.fullmatch(r"https?://[^/]+", base_url):
        raise ValueError("channel base URL must contain only scheme and authority")

    root = channel_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o750)
    destination = root / "artifacts" / str(metadata["filename"])
    atomic_copy(artifact, destination)

    manifest = {
        "version": metadata["version"],
        "released_at": metadata["released_at"],
        "download_url": f"{base_url}/artifacts/{metadata['filename']}",
        "sha256": metadata["sha256"],
        "notes": metadata["notes"],
        "filename": metadata["filename"],
        "size": metadata["size"],
        "candidate_commit": metadata["candidate_commit"],
        "channel": "owner-candidate",
    }
    state = {
        **manifest,
        "manifest_url": f"{base_url}/latest.json",
        "production_version_at_publish": metadata["production_version_at_publish"],
        "channels_separate": True,
    }
    atomic_json(root / "channel-state.json", state)
    atomic_json(root / "latest.json", manifest)
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish an exact artifact to the remote Owner channel.")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--candidate-commit", required=True)
    parser.add_argument("--candidate-version", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--candidate-size", type=int, required=True)
    parser.add_argument("--public-version", required=True)
    parser.add_argument("--channel-root", type=Path, default=DEFAULT_CHANNEL_ROOT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--production-manifest-url", default=PRODUCTION_MANIFEST_URL)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    production_manifest = fetch_json(args.production_manifest_url)
    state = publish(
        artifact=args.artifact,
        source_manifest=args.manifest,
        channel_root=args.channel_root,
        base_url=args.base_url,
        expected_commit=args.candidate_commit,
        expected_version=args.candidate_version,
        expected_sha256=args.candidate_sha256,
        expected_size=args.candidate_size,
        expected_public_version=args.public_version,
        production_manifest=production_manifest,
    )
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
