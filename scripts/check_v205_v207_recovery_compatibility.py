#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile


PUBLIC_V205_SHA256 = "5ae198cb4e92822d4aa88d5ae33871410349cb5e991665df8554d5fdd668e9cb"
PUBLIC_PACKAGE_ROOT = "FedorinovRewards_WebPreview"


UPDATE_HARNESS = r'''
from __future__ import annotations
import hashlib, json, os, pathlib, shutil, socket, subprocess, sys, time

install_root = pathlib.Path(sys.argv[1]).resolve()
candidate_zip = pathlib.Path(sys.argv[2]).resolve()
forced_failure = sys.argv[3] == "1"
workspace = install_root.parent
data_root = workspace / "Rewards"
db_path = data_root / "database" / "MyDatabase.sqlite"
registry = workspace / "runtime"
for name in ("database", "Source", "SourceMark", "default"):
    (data_root / name).mkdir(parents=True, exist_ok=True)
db_path.write_bytes(b"exact temp owner database")
(data_root / "Source" / "owner-photo.jpg").write_bytes(b"exact temp owner photo")
(install_root / ".env").write_text(
    f"REWARDS_DATA_DIR={data_root}\nREWARDS_DB_PATH={db_path}\nAPP_HOST=127.0.0.1\n",
    encoding="utf-8",
)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
os.environ.update({
    "APP_RUNTIME_DIR": str(registry),
    "APP_INSTALL_DIR": str(install_root),
    "APP_HOST": "127.0.0.1",
    "APP_PORT": str(port),
    "REWARDS_DATA_DIR": str(data_root),
    "REWARDS_DB_PATH": str(db_path),
    "READ_ONLY": "true",
    "WRITE_MODE": "false",
    "UPDATE_CHECK_ENABLED": "false",
    "PYTHONDONTWRITEBYTECODE": "1",
})
sys.path.insert(0, str(install_root))
from backend.app.config import Settings
from backend.app.services.runtime_identity import fetch_runtime_identity, process_snapshot
from backend.app.services.runtime_supervisor import RuntimeSupervisor
from backend.app.services.supervised_update import run_supervised_update
from backend.app.services.updater import UpdateError, UpdatePlan

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def data_snapshot():
    return {
        str(path.relative_to(data_root)): digest(path)
        for path in sorted(data_root.rglob("*"))
        if path.is_file()
    }

settings = Settings(
    rewards_data_dir=data_root,
    rewards_db_path=db_path,
    app_host="127.0.0.1",
    app_port=port,
    read_only=True,
    write_mode=False,
    update_check_enabled=True,
    update_manifest_url="https://example.test/latest.json",
    update_timeout_seconds=10,
    app_install_dir=install_root,
    update_backup_dir=install_root / "updates" / "backups",
    update_download_dir=install_root / "updates" / "downloads",
    update_extract_dir=install_root / "updates" / "extracted",
)
supervisor = RuntimeSupervisor(
    registry_dir=registry,
    python_executable=pathlib.Path(sys.executable),
    ready_timeout=8,
)
before = data_snapshot()
old = supervisor.start_or_reuse(
    install_root=install_root,
    host="127.0.0.1",
    port=port,
    expected_version="2.0.5",
)
old_marker = process_snapshot(old.pid).start_marker

candidate_sha = digest(candidate_zip)
def plan_builder(_settings, current):
    return UpdatePlan(current, "2.0.7", True, "https://example.test/v2.0.7.zip", candidate_sha, ["v2.0.7"])
def downloader(_url, destination, _timeout):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate_zip, destination)
    return destination

if forced_failure:
    from backend.app.services import supervised_update as update_module
    original_copy = update_module.copy_package_files
    def broken_copy(package_root, install_dir):
        count = original_copy(package_root, install_dir)
        (install_dir / "scripts" / "runtime_server.py").write_text(
            "#!/usr/bin/env python3\nraise RuntimeError('forced exact-package candidate failure')\n",
            encoding="utf-8",
        )
        return count
    update_module.copy_package_files = broken_copy

try:
    result = run_supervised_update(
        settings,
        requester_pid=old.pid,
        current_version="2.0.5",
        supervisor=supervisor,
        plan_builder=plan_builder,
        zip_downloader=downloader,
    )
except UpdateError as exc:
    if not forced_failure:
        raise
    identity = fetch_runtime_identity("127.0.0.1", port, 0.5)
    if not identity or identity.get("version") != "2.0.5":
        raise AssertionError(f"rollback did not restore v2.0.5: {identity}") from exc
    if data_snapshot() != before:
        raise AssertionError("TEMP data changed during updater rollback")
    healthy = [item for item in supervisor.inspect_all() if item.confirmed and item.healthy]
    if len(healthy) != 1 or healthy[0].record.pid != identity["pid"]:
        raise AssertionError("rollback did not leave exactly one healthy v2.0.5 backend")
    supervisor.stop_all_confirmed()
    print(json.dumps({"ok": True, "rollback": True, "identity": identity}, ensure_ascii=False))
    raise SystemExit(0)

if forced_failure:
    raise AssertionError("forced failure unexpectedly succeeded")
identity = fetch_runtime_identity("127.0.0.1", port, 0.5)
if not identity or identity.get("version") != "2.0.7":
    raise AssertionError(f"public v2.0.5 updater did not start v2.0.7: {identity}")
if identity.get("pid") == old.pid or process_snapshot(old.pid) is not None and process_snapshot(old.pid).start_marker == old_marker:
    raise AssertionError("old v2.0.5 PID survived successful update")
if data_snapshot() != before:
    raise AssertionError("TEMP data changed during public v2.0.5 update")
repeat = subprocess.run(
    [sys.executable, str(install_root / "scripts" / "runtime_bootstrap.py"), "start"],
    cwd=install_root,
    env=os.environ.copy(),
    text=True,
    capture_output=True,
    timeout=60,
    check=True,
)
repeat_evidence = json.loads(repeat.stdout.splitlines()[-1])
if not repeat_evidence.get("reused") or repeat_evidence.get("pid") != identity.get("pid"):
    raise AssertionError(f"repeat launch did not reuse v2.0.7: {repeat_evidence}")
healthy = [item for item in supervisor.inspect_all() if item.confirmed and item.healthy]
if len(healthy) != 1 or healthy[0].record.pid != identity["pid"]:
    raise AssertionError("successful update did not leave exactly one healthy backend")
supervisor.stop_all_confirmed()
print(json.dumps({
    "ok": True,
    "rollback": False,
    "old_pid": old.pid,
    "new_identity": identity,
    "repeat": repeat_evidence,
    "backup_path": result.get("backup_path"),
    "data": before,
}, ensure_ascii=False))
'''


RECOVERY_HARNESS = r'''
from __future__ import annotations
import hashlib, importlib.util, json, os, pathlib, socket, sys

install_root = pathlib.Path(sys.argv[1]).resolve()
service_dir = pathlib.Path(sys.argv[2]).resolve()
forced_failure = sys.argv[3] == "1"
workspace = install_root.parent
data_root = workspace / "Rewards"
db_path = data_root / "database" / "MyDatabase.sqlite"
registry = workspace / "runtime"
pointer = workspace / "installation.json"
for name in ("database", "Source", "SourceMark", "default"):
    (data_root / name).mkdir(parents=True, exist_ok=True)
db_path.write_bytes(b"exact temp recovery database")
(data_root / "Source" / "owner-photo.jpg").write_bytes(b"exact temp recovery photo")
(install_root / ".env").write_text(
    f"REWARDS_DATA_DIR={data_root}\nREWARDS_DB_PATH={db_path}\nAPP_HOST=127.0.0.1\n",
    encoding="utf-8",
)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
with (install_root / ".env").open("a", encoding="utf-8") as handle:
    handle.write(f"APP_PORT={port}\n")
os.environ.update({
    "APP_RUNTIME_DIR": str(registry),
    "APP_INSTALLATION_POINTER": str(pointer),
    "REWARDS_DATA_DIR": str(data_root),
    "REWARDS_DB_PATH": str(db_path),
    "READ_ONLY": "true",
    "WRITE_MODE": "false",
    "UPDATE_CHECK_ENABLED": "false",
    "PYTHONDONTWRITEBYTECODE": "1",
})
spec = importlib.util.spec_from_file_location("exact_recovery", service_dir / "recovery_v207.py")
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def data_snapshot():
    return {
        str(path.relative_to(data_root)): digest(path)
        for path in sorted(data_root.rglob("*"))
        if path.is_file()
    }

package = module.load_recovery_package(service_dir)
candidate = module.validate_installation(install_root, supported_versions=module.SUPPORTED_SOURCE_VERSIONS)
if candidate is None:
    raise AssertionError("exact public v2.0.5 install was not recognized")
before = data_snapshot()
stage = workspace / "stage"
package_root = module.validate_and_extract_package(package, stage)
if forced_failure:
    (package_root / "scripts" / "runtime_server.py").write_text(
        "#!/usr/bin/env python3\nraise RuntimeError('forced exact-recovery candidate failure')\n",
        encoding="utf-8",
    )

try:
    result = module.run_recovery_transaction(
        candidate,
        package,
        package_root,
        registry_dir=registry,
        start_fn=module.start_runtime,
    )
except module.RecoveryError as exc:
    if not forced_failure:
        raise
    _, restored_version = module._version_metadata(install_root / "backend/app/version.py")
    identity = module._fetch_identity(candidate.host, candidate.port, 0.5)
    if restored_version != "2.0.5" or not identity or identity.get("version") != "2.0.5":
        raise AssertionError(f"recovery rollback did not restore running v2.0.5: {restored_version}, {identity}") from exc
    if data_snapshot() != before:
        raise AssertionError("TEMP data changed during recovery rollback")
    module._run_internal_stop(candidate, registry)
    print(json.dumps({"ok": True, "rollback": True, "identity": identity}, ensure_ascii=False))
    raise SystemExit(0)

if forced_failure:
    raise AssertionError("forced recovery failure unexpectedly succeeded")
identity = module._fetch_identity(candidate.host, candidate.port, 0.5)
if not identity or identity.get("version") != "2.0.7":
    raise AssertionError(f"recovery did not start v2.0.7: {identity}")
if data_snapshot() != before or result.get("data_before") != result.get("data_after"):
    raise AssertionError("TEMP data changed during recovery")
if not pathlib.Path(result["backup_path"]).is_file() or not pointer.is_file():
    raise AssertionError("recovery did not preserve backup/pointer evidence")
module._run_internal_stop(candidate, registry)
print(json.dumps({"ok": True, "rollback": False, "identity": identity, "result": result}, ensure_ascii=False))
'''


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_extract_public(zip_path: Path, destination: Path) -> Path:
    with ZipFile(zip_path) as archive:
        for member in archive.infolist():
            parts = tuple(part for part in member.filename.replace("\\", "/").split("/") if part)
            if not parts or parts[0] != PUBLIC_PACKAGE_ROOT or ".." in parts:
                raise RuntimeError(f"unsafe public package member: {member.filename}")
        archive.extractall(destination)
    root = destination / PUBLIC_PACKAGE_ROOT
    if not (root / "backend/app/version.py").is_file():
        raise RuntimeError("public package root is incomplete")
    return root


def _safe_extract_recovery(zip_path: Path, destination: Path) -> Path:
    with ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        required = {"service/recovery_v207.py", "service/manifest.json"}
        if not required.issubset(names) or any(".." in Path(name).parts for name in names):
            raise RuntimeError("recovery package root is incomplete or unsafe")
        archive.extractall(destination)
    return destination / "service"


def _run_harness(source: str, *args: Path | bool) -> dict[str, object]:
    values = [str(value) if not isinstance(value, bool) else ("1" if value else "0") for value in args]
    result = subprocess.run(
        [sys.executable, "-c", source, *values],
        text=True,
        capture_output=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "compatibility harness failed")
    try:
        return json.loads(result.stdout.splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"compatibility harness returned invalid evidence: {result.stdout}") from exc


def run_checks(public_v205: Path, candidate: Path, recovery: Path, cycles: int) -> dict[str, object]:
    if sha256_file(public_v205) != PUBLIC_V205_SHA256:
        raise RuntimeError("public v2.0.5 ZIP checksum mismatch")
    for path in (candidate, recovery):
        if not path.is_file():
            raise FileNotFoundError(path)
    updates: list[dict[str, object]] = []
    recoveries: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="ale327-v205-contract-") as tmpdir:
        root = Path(tmpdir)
        service = _safe_extract_recovery(recovery, root / "recovery")
        for index in range(cycles):
            update_install = _safe_extract_public(public_v205, root / f"update-{index}")
            updates.append(_run_harness(UPDATE_HARNESS, update_install, candidate, False))
            recovery_install = _safe_extract_public(public_v205, root / f"recovery-{index}")
            recoveries.append(_run_harness(RECOVERY_HARNESS, recovery_install, service, False))
        update_rollback_install = _safe_extract_public(public_v205, root / "update-rollback")
        update_rollback = _run_harness(UPDATE_HARNESS, update_rollback_install, candidate, True)
        recovery_rollback_install = _safe_extract_public(public_v205, root / "recovery-rollback")
        recovery_rollback = _run_harness(RECOVERY_HARNESS, recovery_rollback_install, service, True)
    return {
        "public_v205_sha256": PUBLIC_V205_SHA256,
        "candidate_sha256": sha256_file(candidate),
        "recovery_sha256": sha256_file(recovery),
        "cycles": cycles,
        "updates": updates,
        "recoveries": recoveries,
        "update_rollback": update_rollback,
        "recovery_rollback": recovery_rollback,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify exact public v2.0.5 updater and v2.0.7 recovery contracts.")
    parser.add_argument("--public-v205", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--recovery", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=5)
    args = parser.parse_args(argv)
    if args.cycles < 1:
        parser.error("--cycles must be positive")
    try:
        result = run_checks(
            args.public_v205.resolve(strict=False),
            args.candidate.resolve(strict=False),
            args.recovery.resolve(strict=False),
            args.cycles,
        )
    except (FileNotFoundError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
