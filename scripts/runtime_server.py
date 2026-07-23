#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--startup-path", type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-build-id", required=True)
    return parser


def _resolve_runtime_paths(state_path: Path, startup_path: Path | None, instance_token: str) -> tuple[Path, Path]:
    from backend.app.services.runtime_identity import runtime_state_path
    from backend.app.services.runtime_startup import runtime_startup_path

    resolved_state = state_path.resolve(strict=False)
    registry_dir = resolved_state.parent
    configured_registry = os.getenv("APP_RUNTIME_DIR", "").strip()
    if not configured_registry:
        raise RuntimeError("APP_RUNTIME_DIR is required for managed runtime startup")
    expected_registry = Path(os.path.expandvars(configured_registry)).expanduser().resolve(strict=False)
    if registry_dir != expected_registry:
        raise RuntimeError(f"Runtime registry path mismatch: {registry_dir} != {expected_registry}")
    expected_state = runtime_state_path(registry_dir, instance_token).resolve(strict=False)
    if resolved_state != expected_state:
        raise RuntimeError(f"Runtime state path mismatch: {resolved_state} != {expected_state}")

    expected_startup = runtime_startup_path(registry_dir, instance_token).resolve(strict=False)
    if startup_path is not None and startup_path.resolve(strict=False) != expected_startup:
        raise RuntimeError(
            f"Runtime startup path mismatch: {startup_path.resolve(strict=False)} != {expected_startup}"
        )
    return resolved_state, expected_startup


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    legacy_runtime_contract = args.startup_path is None
    install_root = args.install_root.resolve(strict=False)
    state_path, startup_path = _resolve_runtime_paths(
        args.state_path,
        args.startup_path,
        args.instance_token,
    )
    os.environ.update(
        {
            "APP_HOST": args.host,
            "APP_PORT": str(args.port),
            "APP_INSTALL_DIR": str(install_root),
            "APP_INSTANCE_TOKEN": args.instance_token,
            "APP_RUNTIME_STATE_PATH": str(state_path),
            "APP_RUNTIME_STARTUP_PATH": str(startup_path),
        }
    )

    from backend.app.services.runtime_identity import register_current_runtime, remove_runtime_state, runtime_build_id
    from backend.app.services.runtime_startup import RuntimeStartupReporter
    from backend.app.version import APP_VERSION

    reporter = RuntimeStartupReporter(
        path=startup_path,
        instance_token=args.instance_token,
        install_root=install_root,
        host=args.host,
        port=args.port,
        expected_version=args.expected_version,
        expected_build_id=args.expected_build_id,
    )
    record = None
    failed = False
    try:
        reporter.stage("validating-install-root")
        if install_root != SCRIPT_ROOT:
            raise RuntimeError(f"Runtime install root mismatch: {install_root} != {SCRIPT_ROOT}")

        reporter.stage("validating-version")
        if APP_VERSION != args.expected_version:
            raise RuntimeError(f"Runtime version mismatch: {APP_VERSION} != {args.expected_version}")

        reporter.stage("validating-build")
        build_id = runtime_build_id(install_root)
        if build_id != args.expected_build_id:
            raise RuntimeError(f"Runtime build mismatch: {build_id} != {args.expected_build_id}")

        reporter.stage("registering-identity")
        record = register_current_runtime(
            install_root=install_root,
            host=args.host,
            port=args.port,
            version=APP_VERSION,
            build_id=build_id,
            instance_token=args.instance_token,
            state_path=state_path,
            prepare_legacy_inspection=os.name == "nt" and legacy_runtime_contract,
        )

        reporter.stage("loading-server")
        import uvicorn
        from backend.app.main import app

        reporter.stage("binding-port")
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            access_log=False,
            log_level="info",
        )
    except BaseException as exc:
        failed = True
        reporter.failed(exc)
        print(
            json.dumps(
                {
                    "event": "runtime-startup-failed",
                    "error_type": exc.__class__.__name__,
                    "error": str(exc) or repr(exc),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
            flush=True,
        )
        raise
    finally:
        if failed:
            reporter.stop()
        else:
            reporter.remove()
        if record is not None:
            remove_runtime_state(
                state_path,
                pid=record.pid,
                instance_token=record.instance_token,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
