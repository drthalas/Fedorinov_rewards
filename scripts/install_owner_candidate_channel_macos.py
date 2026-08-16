#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
from typing import List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LABEL = "com.fedorinov.owner-candidate-channel"
DEFAULT_ROOT = (
    Path.home() / "Library" / "Application Support" / "FedorinovRewards" / "owner-candidate-channel"
)


def launch_agent(root: Path, python: Path, port: int, trusted_lan: str) -> dict[str, object]:
    server = root / "bin" / "owner_candidate_channel_server.py"
    logs = root / "logs"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(python),
            str(server),
            "--root",
            str(root),
            "--bind",
            "0.0.0.0",
            "--port",
            str(port),
            "--allowed-network",
            "127.0.0.0/8",
            "--allowed-network",
            trusted_lan,
        ],
        "WorkingDirectory": str(root),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(logs / "server.stdout.log"),
        "StandardErrorPath": str(logs / "server.stderr.log"),
    }


def install(root: Path, python: Path, port: int, trusted_lan: str, *, load: bool) -> Path:
    root = root.expanduser().resolve()
    for directory in (root, root / "bin", root / "artifacts", root / "logs"):
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o750)
    source = PROJECT_ROOT / "scripts" / "owner_candidate_channel_server.py"
    destination = root / "bin" / source.name
    shutil.copy2(source, destination)
    os.chmod(destination, 0o750)

    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = plist_path.with_suffix(".plist.tmp")
    temporary.write_bytes(plistlib.dumps(launch_agent(root, python, port, trusted_lan)))
    os.chmod(temporary, 0o600)
    os.replace(temporary, plist_path)

    if load:
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(plist_path)], check=False)
        subprocess.run(["launchctl", "bootstrap", domain, str(plist_path)], check=True)
        subprocess.run(["launchctl", "enable", f"{domain}/{LABEL}"], check=True)
        subprocess.run(["launchctl", "kickstart", "-k", f"{domain}/{LABEL}"], check=True)
    return plist_path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Install the Owner candidate channel LaunchAgent.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--python", type=Path, default=Path("/usr/bin/python3"))
    parser.add_argument("--port", type=int, default=18387)
    parser.add_argument("--trusted-lan", default="192.168.1.0/24")
    parser.add_argument("--no-load", action="store_true")
    args = parser.parse_args(argv)
    if not args.python.is_file():
        parser.error(f"Python executable not found: {args.python}")
    path = install(args.root, args.python, args.port, args.trusted_lan, load=not args.no_load)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
