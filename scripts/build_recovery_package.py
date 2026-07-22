#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = PROJECT_ROOT / "dist"
RECOVERY_SOURCE_ROOT = PROJECT_ROOT / "recovery"
SERVICE_SOURCE = PROJECT_ROOT / "scripts" / "recovery_v206.py"
MAIN_PACKAGE_BASENAME = "FedorinovRewards_WebPreview"
RECOVERY_PACKAGE_BASENAME = "FedorinovRewards_Recovery"
USER_FILES = (
    "ВОССТАНОВИТЬ_И_ЗАПУСТИТЬ_2.0.6.bat",
    "ИНСТРУКЦИЯ.txt",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recovery_zip_path(version: str) -> Path:
    return DIST_ROOT / f"{RECOVERY_PACKAGE_BASENAME}_v{version}.zip"


def main_zip_path(version: str) -> Path:
    return DIST_ROOT / f"{MAIN_PACKAGE_BASENAME}_v{version}.zip"


def build_recovery_package(version: str, *, main_package: Path | None = None) -> dict[str, object]:
    if version != "2.0.6":
        raise ValueError("This recovery package is intentionally scoped to v2.0.6.")
    main_zip = (main_package or main_zip_path(version)).resolve(strict=False)
    if not main_zip.is_file():
        raise FileNotFoundError(f"main release package is missing: {main_zip}")
    requirements = PROJECT_ROOT / "backend" / "requirements.txt"
    service_root = DIST_ROOT / f".{RECOVERY_PACKAGE_BASENAME}_v{version}"
    if service_root.exists():
        shutil.rmtree(service_root)
    (service_root / "service").mkdir(parents=True)

    for filename in USER_FILES:
        shutil.copy2(RECOVERY_SOURCE_ROOT / filename, service_root / filename)
    shutil.copy2(SERVICE_SOURCE, service_root / "service" / SERVICE_SOURCE.name)
    shutil.copy2(main_zip, service_root / "service" / main_zip.name)

    manifest = {
        "schema": 1,
        "application_id": "fedorinov-rewards-recovery",
        "version": version,
        "package_filename": main_zip.name,
        "package_size": main_zip.stat().st_size,
        "package_sha256": sha256_file(main_zip),
        "requirements_sha256": sha256_file(requirements),
        "supported_source_versions": ["2.0.5"],
    }
    manifest_path = service_root / "service" / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    target = recovery_zip_path(version)
    if target.exists():
        target.unlink()
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in sorted(service_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(service_root))
    shutil.rmtree(service_root)
    return {
        "version": version,
        "zip_path": str(target),
        "size_bytes": target.stat().st_size,
        "sha256": sha256_file(target),
        "main_package_sha256": manifest["package_sha256"],
        "members": 5,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the one-time v2.0.6 recovery package.")
    parser.add_argument("--version", default="2.0.6")
    parser.add_argument("--main-package", type=Path)
    args = parser.parse_args(argv)
    try:
        result = build_recovery_package(args.version, main_package=args.main_package)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
