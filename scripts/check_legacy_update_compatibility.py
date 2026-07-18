#!/usr/bin/env python3
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_TAG = "v0.1.14"
LEGACY_COMMIT = "53bb35579aeb8a0c26a38c04019de7f7df36645a"


HARNESS = r'''
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from shutil import copytree
import subprocess
import sys
from unittest.mock import patch
from zipfile import ZipFile

legacy_root = Path(sys.argv[1]).resolve()
failed_zip = Path(sys.argv[2]).resolve()
candidate_zip = Path(sys.argv[3]).resolve()
sys.path.insert(0, str(legacy_root))

from backend.app.config import Settings
from backend.app.services import updater


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


data_root = legacy_root.parent / "user-data"
db_path = data_root / "database" / "MyDatabase.sqlite"
person_photo = data_root / "Source" / "77" / "person-photo.jpg"
person_document = data_root / "Source" / "77" / "document.txt"
mark_photo = data_root / "SourceMark" / "1" / "mark-photo.jpg"
for path, payload in (
    (db_path, b"test database stays unchanged"),
    (person_photo, b"test person photo stays unchanged"),
    (person_document, b"test person document stays unchanged"),
    (mark_photo, b"test mark photo stays unchanged"),
):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)

(legacy_root / ".env").write_text(f"REWARDS_DATA_DIR={data_root}\n", encoding="utf-8")
data_before = {str(path.relative_to(data_root)): digest(path) for path in (db_path, person_photo, person_document, mark_photo)}

settings = Settings(
    rewards_data_dir=data_root,
    rewards_db_path=db_path,
    read_only=False,
    write_mode=True,
    require_backup_before_write=False,
    require_backup_before_dangerous_actions=False,
    update_check_enabled=True,
    update_manifest_url="https://example.test/latest.json",
    update_timeout_seconds=10,
    app_install_dir=legacy_root,
    update_backup_dir=legacy_root / "updates" / "backups",
    update_download_dir=legacy_root / "updates" / "downloads",
    update_extract_dir=legacy_root / "updates" / "extracted",
)

downloads = []


def manifest(version: str, zip_path: Path) -> dict[str, object]:
    return {
        "enabled": True,
        "update_available": True,
        "current_version": "0.1.14",
        "latest_version": version,
        "download_url": f"https://example.test/FedorinovRewards_WebPreview_v{version}.zip",
        "sha256": digest(zip_path),
        "notes": [version],
        "error": None,
    }


def downloader_for(source: Path):
    def download(url: str, destination: Path, timeout: int) -> Path:
        downloads.append({"url": url, "destination": destination.name, "sha256": digest(source)})
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        return destination
    return download


failure = None
with patch.object(updater, "check_for_updates", return_value=manifest("2.0.0", failed_zip)):
    try:
        updater.apply_update(settings, current_version="0.1.14", zip_downloader=downloader_for(failed_zip))
    except updater.UpdateError as exc:
        failure = str(exc)
if not failure or "forbidden file type" not in failure:
    raise AssertionError(f"v2.0.0 did not reproduce the legacy validation failure: {failure}")
if settings.update_backup_dir.exists() and any(settings.update_backup_dir.iterdir()):
    raise AssertionError("backup was created before legacy validation failed")
if updater.read_update_status(settings).get("status") != "error":
    raise AssertionError("failed attempt did not leave a retryable error status")

with patch.object(updater, "check_for_updates", return_value=manifest("2.0.2", candidate_zip)):
    result = updater.apply_update(
        settings,
        current_version="0.1.14",
        zip_downloader=downloader_for(candidate_zip),
    )
if not result.get("ok"):
    raise AssertionError(f"v2.0.2 legacy apply failed: {result}")

styles = (legacy_root / "backend" / "app" / "static" / "styles.css").read_text(encoding="utf-8")
if styles.count(";base64,") != 6:
    raise AssertionError("installed CSS does not contain all six embedded UI assets")
if "/static/assets/cavaliers/" in styles or "/static/assets/guides/" in styles:
    raise AssertionError("installed CSS still depends on unpackaged binary UI assets")
if "APP_VERSION = \"2.0.2\"" not in (legacy_root / "backend" / "app" / "version.py").read_text(encoding="utf-8"):
    raise AssertionError("installed version source is not 2.0.2")

data_after = {str(path.relative_to(data_root)): digest(path) for path in (db_path, person_photo, person_document, mark_photo)}
if data_after != data_before:
    raise AssertionError("temp user DB/media changed during update")
if (legacy_root / ".env").read_text(encoding="utf-8") != f"REWARDS_DATA_DIR={data_root}\n":
    raise AssertionError("local .env changed during update")

backup_path = Path(str(result["backup_path"]))
with ZipFile(backup_path) as backup:
    backup_names = set(backup.namelist())
if "backend/app/version.py" not in backup_names or ".env" in backup_names:
    raise AssertionError("backup contents are not safe/usable")

rollback_root = legacy_root.parent / "rollback-copy"
copytree(legacy_root, rollback_root, ignore=lambda _dir, names: {"updates"} if "updates" in names else set())
updater.restore_backup(backup_path, rollback_root)
rollback_version = (rollback_root / "backend" / "app" / "version.py").read_text(encoding="utf-8")
if "APP_VERSION = \"0.1.14\"" not in rollback_version:
    raise AssertionError("backup rollback did not restore legacy application version")

restart_code = """
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from backend.app.services.update_checker import check_for_updates
from backend.app.config import Settings
from backend.app.version import APP_VERSION
settings = Settings(rewards_data_dir=root.parent/'user-data', rewards_db_path=root.parent/'user-data/database/MyDatabase.sqlite', update_check_enabled=True, update_manifest_url='https://example.test/latest.json')
manifest = json.dumps({'version': '2.0.2', 'download_url': 'https://example.test/v2.0.2.zip', 'sha256': 'a'*64}).encode()
check = check_for_updates(settings, current_version=APP_VERSION, fetcher=lambda _url, _timeout: manifest)
print(json.dumps({'version': APP_VERSION, 'update_available': check['update_available']}))
"""
restart = subprocess.run([sys.executable, "-c", restart_code, str(legacy_root)], text=True, capture_output=True, check=True)
restart_result = json.loads(restart.stdout)
if restart_result != {"version": "2.0.2", "update_available": False}:
    raise AssertionError(f"restart/update-check validation failed: {restart_result}")

if [item["destination"] for item in downloads] != [
    "FedorinovRewards_WebPreview_v2.0.0.zip",
    "FedorinovRewards_WebPreview_v2.0.2.zip",
]:
    raise AssertionError(f"retry reused a stale download path: {downloads}")

print(json.dumps({
    "legacy_failure": failure,
    "backup_path": str(backup_path),
    "backup_members": len(backup_names),
    "copied_files": result["copied_files"],
    "downloads": downloads,
    "data_before": data_before,
    "data_after": data_after,
    "restart": restart_result,
    "rollback_version": "0.1.14",
    "embedded_assets": 6,
}, ensure_ascii=False))
'''


def _export_legacy_tree(destination: Path) -> None:
    result = subprocess.run(
        ["git", "archive", "--format=tar", LEGACY_TAG],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
    )
    with tarfile.open(fileobj=BytesIO(result.stdout), mode="r:") as archive:
        archive.extractall(destination)


def run_check(failed_zip: Path, candidate_zip: Path) -> dict[str, object]:
    actual_commit = subprocess.run(
        ["git", "rev-parse", f"{LEGACY_TAG}^{{commit}}"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    if actual_commit != LEGACY_COMMIT:
        raise RuntimeError(f"unexpected {LEGACY_TAG} target: {actual_commit}")
    for path in (failed_zip, candidate_zip):
        if not path.is_file():
            raise FileNotFoundError(path)

    with TemporaryDirectory(prefix="ale253-legacy-upgrade-") as tmpdir:
        legacy_root = Path(tmpdir) / "legacy-install"
        legacy_root.mkdir()
        _export_legacy_tree(legacy_root)
        result = subprocess.run(
            [sys.executable, "-c", HARNESS, str(legacy_root), str(failed_zip), str(candidate_zip)],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "legacy compatibility harness failed")
        payload = json.loads(result.stdout)
        payload.update({"legacy_tag": LEGACY_TAG, "legacy_commit": LEGACY_COMMIT})
        return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the v0.1.14 retry/update flow against a release candidate.")
    parser.add_argument("--failed-v2-zip", required=True, type=Path)
    parser.add_argument("--candidate-zip", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_check(args.failed_v2_zip.resolve(), args.candidate_zip.resolve())
    except (FileNotFoundError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
