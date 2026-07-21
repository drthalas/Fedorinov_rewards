#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one identity-managed Fedorinov Rewards backend.")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--install-root", required=True, type=Path)
    parser.add_argument("--instance-token", required=True)
    parser.add_argument("--state-path", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-build-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    install_root = args.install_root.resolve(strict=False)
    if install_root != SCRIPT_ROOT:
        raise SystemExit(f"Runtime install root mismatch: {install_root} != {SCRIPT_ROOT}")

    os.environ.update(
        {
            "APP_HOST": args.host,
            "APP_PORT": str(args.port),
            "APP_INSTALL_DIR": str(install_root),
            "APP_INSTANCE_TOKEN": args.instance_token,
            "APP_RUNTIME_STATE_PATH": str(args.state_path.resolve(strict=False)),
        }
    )

    from backend.app.services.runtime_identity import register_current_runtime, remove_runtime_state, runtime_build_id
    from backend.app.version import APP_VERSION

    if APP_VERSION != args.expected_version:
        raise SystemExit(f"Runtime version mismatch: {APP_VERSION} != {args.expected_version}")
    build_id = runtime_build_id(install_root)
    if build_id != args.expected_build_id:
        raise SystemExit(f"Runtime build mismatch: {build_id} != {args.expected_build_id}")

    record = register_current_runtime(
        install_root=install_root,
        host=args.host,
        port=args.port,
        version=APP_VERSION,
        build_id=build_id,
        instance_token=args.instance_token,
        state_path=args.state_path,
    )
    try:
        import uvicorn

        uvicorn.run(
            "backend.app.main:app",
            host=args.host,
            port=args.port,
            access_log=False,
            log_level="info",
        )
    finally:
        remove_runtime_state(
            args.state_path,
            pid=record.pid,
            instance_token=record.instance_token,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
