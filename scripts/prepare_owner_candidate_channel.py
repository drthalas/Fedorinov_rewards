from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.request import Request, urlopen
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MANIFEST_URL = (
    "https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json"
)
DEFAULT_HOST = "fedorinov-win-gate"
DEFAULT_CHANNEL_ROOT = r"C:\FedorinovGate\OwnerCandidateChannel"
DEFAULT_PUBLIC_INSTALL = r"C:\Users\codex\Desktop\Fedorinov Rewards - Public Current"
DEFAULT_PORT = 18387


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def validate_candidate(
    *,
    artifact: Path,
    manifest_path: Path,
    expected_commit: str,
    expected_version: str,
    expected_sha256: str,
    expected_public_version: str,
    production_manifest: dict[str, Any],
    candidate_port: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
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
    manifest = load_json(manifest_path.resolve(strict=True))
    artifact_sha = sha256(artifact)
    if artifact_sha != expected_sha256:
        raise ValueError(f"candidate SHA mismatch: expected {expected_sha256}, got {artifact_sha}")
    if package_version(artifact) != expected_version:
        raise ValueError("candidate ZIP version does not match expected version")
    if str(manifest.get("version")) != expected_version:
        raise ValueError("candidate manifest version does not match expected version")
    if str(manifest.get("sha256")) != expected_sha256:
        raise ValueError("candidate manifest SHA does not match expected SHA")
    if str(production_manifest.get("version")) != expected_public_version:
        raise ValueError(
            "production manifest version mismatch: "
            f"expected {expected_public_version}, got {production_manifest.get('version')}"
        )
    if expected_public_version == expected_version:
        raise ValueError("candidate must not equal the current public version")

    owner_manifest = dict(manifest)
    owner_manifest["download_url"] = f"http://127.0.0.1:{candidate_port}/{artifact.name}"
    evidence = {
        "candidate_commit": expected_commit,
        "candidate_version": expected_version,
        "candidate_filename": artifact.name,
        "candidate_size": artifact.stat().st_size,
        "candidate_sha256": artifact_sha,
        "public_version": expected_public_version,
        "production_manifest_url": PRODUCTION_MANIFEST_URL,
        "candidate_manifest_url": f"http://127.0.0.1:{candidate_port}/latest.json",
        "channels_separate": True,
    }
    return owner_manifest, evidence


def check_host(host: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", host):
        raise ValueError("SSH host must be a configured alias or hostname")


def decode_windows_output(value: bytes) -> str:
    for encoding in ("utf-8", "cp866", "cp1251"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def run(command: list[str]) -> str:
    result = subprocess.run(command, check=False, capture_output=True)
    stdout = decode_windows_output(result.stdout).strip()
    stderr = decode_windows_output(result.stderr).strip()
    if result.returncode:
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"command failed: {command[0]}: {detail}")
    return stdout


def parse_last_json(output: str) -> dict[str, Any]:
    for line in reversed(output.splitlines()):
        try:
            value = json.loads(line.lstrip("\ufeff"))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError(f"remote command did not return JSON: {output}")


def remote_control(host: str, action: str, channel_root: str) -> dict[str, Any]:
    script = channel_root + r"\configure_owner_candidate_channel.ps1"
    state = channel_root + r"\channel-state.json"
    output = run(
        [
            "ssh",
            host,
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script,
            "-Action",
            action,
            "-SpecPath",
            state,
        ]
    )
    return parse_last_json(output)


def deploy(args: argparse.Namespace) -> dict[str, Any]:
    check_host(args.host)
    production_manifest = fetch_json(args.production_manifest_url)
    owner_manifest, evidence = validate_candidate(
        artifact=args.artifact,
        manifest_path=args.manifest,
        expected_commit=args.candidate_commit,
        expected_version=args.candidate_version,
        expected_sha256=args.candidate_sha256,
        expected_public_version=args.public_version,
        production_manifest=production_manifest,
        candidate_port=args.port,
    )
    if args.dry_run:
        return {"action": "dry-run", **evidence}

    remote_incoming = args.channel_root + r"\incoming"
    mkdir_command = (
        "$ErrorActionPreference='Stop';"
        f"New-Item -ItemType Directory -Path '{remote_incoming}' -Force | Out-Null"
    )
    run(["ssh", args.host, "powershell.exe", "-NoProfile", "-Command", mkdir_command])

    with tempfile.TemporaryDirectory(prefix="owner-candidate-channel-") as temp_dir:
        temp = Path(temp_dir)
        local_manifest = temp / "latest.json"
        local_spec = temp / "deploy-spec.json"
        local_manifest.write_text(
            json.dumps(owner_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        spec = {
            "schema_version": 1,
            "candidate_commit": args.candidate_commit,
            "candidate_version": args.candidate_version,
            "candidate_sha256": args.candidate_sha256,
            "candidate_filename": args.artifact.name,
            "candidate_port": args.port,
            "production_manifest_url": args.production_manifest_url,
            "expected_public_version": args.public_version,
            "public_install_root": args.public_install_root,
            "channel_root": args.channel_root,
        }
        local_spec.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        files = {
            args.artifact: args.artifact.name,
            local_manifest: "latest.json",
            local_spec: "deploy-spec.json",
            PROJECT_ROOT / "scripts" / "owner_candidate_channel_server.py": "owner_candidate_channel_server.py",
            PROJECT_ROOT / "scripts" / "configure_owner_candidate_channel.ps1": "configure_owner_candidate_channel.ps1",
            PROJECT_ROOT / "scripts" / "verify_owner_candidate_visibility.py": "verify_owner_candidate_visibility.py",
            PROJECT_ROOT / "scripts" / "verify_owner_candidate_handoff.ps1": "verify_owner_candidate_handoff.ps1",
        }
        for source, name in files.items():
            run(["scp", str(source), f"{args.host}:{remote_incoming.replace(chr(92), '/')}/{name}"])

    remote_script = remote_incoming + r"\configure_owner_candidate_channel.ps1"
    remote_spec = remote_incoming + r"\deploy-spec.json"
    output = run(
        [
            "ssh",
            args.host,
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            remote_script,
            "-Action",
            "Deploy",
            "-SpecPath",
            remote_spec,
        ]
    )
    remote = parse_last_json(output)
    handoff_script = args.channel_root + r"\verify_owner_candidate_handoff.ps1"
    visibility_output = run(
        [
            "ssh",
            args.host,
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            handoff_script,
            "-ChannelRoot",
            args.channel_root,
        ]
    )
    return {
        **evidence,
        "remote": remote,
        "physical_visibility": parse_last_json(visibility_output),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the isolated physical Owner candidate channel.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--channel-root", default=DEFAULT_CHANNEL_ROOT)
    subparsers = parser.add_subparsers(dest="action", required=True)

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.add_argument("--artifact", type=Path, required=True)
    deploy_parser.add_argument("--manifest", type=Path, required=True)
    deploy_parser.add_argument("--candidate-commit", required=True)
    deploy_parser.add_argument("--candidate-version", required=True)
    deploy_parser.add_argument("--candidate-sha256", required=True)
    deploy_parser.add_argument("--public-version", required=True)
    deploy_parser.add_argument("--public-install-root", default=DEFAULT_PUBLIC_INSTALL)
    deploy_parser.add_argument("--production-manifest-url", default=PRODUCTION_MANIFEST_URL)
    deploy_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    deploy_parser.add_argument("--dry-run", action="store_true")

    subparsers.add_parser("status")
    subparsers.add_parser("restore")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.action == "deploy":
        result = deploy(args)
    else:
        check_host(args.host)
        result = remote_control(args.host, args.action.capitalize(), args.channel_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
