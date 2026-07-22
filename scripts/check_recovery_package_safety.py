#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat
import sys
from zipfile import BadZipFile, ZipFile, ZipInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.update_archive_policy import validate_zip_members  # noqa: E402


SUPPORTED_SOURCE_VERSIONS = {
    "2.0.6": ["2.0.5"],
    "2.0.7": ["2.0.5", "2.0.6"],
}


def expected_root_files(version: str) -> set[str]:
    return {f"ВОССТАНОВИТЬ_И_ЗАПУСТИТЬ_{version}.bat", "ИНСТРУКЦИЯ.txt"}


def expected_service_files(version: str) -> set[str]:
    compact = version.replace(".", "")
    return {
        f"service/recovery_v{compact}.py",
        "service/manifest.json",
        f"service/FedorinovRewards_WebPreview_v{version}.zip",
    }


# Compatibility aliases for the immutable v2.0.6 package tests.
ROOT_FILES = expected_root_files("2.0.6")
SERVICE_FILES = expected_service_files("2.0.6")


def _is_special(member: ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    return bool(file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)))


def _validate_corrective_bootstrap(content: bytes) -> None:
    if content.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        raise RuntimeError("corrective recovery bootstrap must not contain a BOM")
    if not content.isascii():
        raise RuntimeError("corrective recovery bootstrap must be ASCII-only")
    if b"\r\n" not in content or content.replace(b"\r\n", b"").find(b"\n") >= 0:
        raise RuntimeError("corrective recovery bootstrap must use CRLF only")
    if b"\r" in content.replace(b"\r\n", b""):
        raise RuntimeError("corrective recovery bootstrap contains a bare CR")
    text = content.decode("ascii")
    forbidden = ("chcp", "(", ")", "EnableDelayedExpansion", "powershell")
    if any(value.casefold() in text.casefold() for value in forbidden):
        raise RuntimeError("corrective recovery bootstrap contains parser-sensitive control flow")
    required = ("%~dp0", "recovery_v207.py", "--service-dir", "exit /b")
    if any(value not in text for value in required):
        raise RuntimeError("corrective recovery bootstrap contract is incomplete")


def check_recovery_package(path: Path) -> dict[str, object]:
    with ZipFile(path) as archive:
        if archive.testzip():
            raise RuntimeError("recovery ZIP has a corrupt member")
        members = [member for member in archive.infolist() if not member.is_dir()]
        names = {member.filename.replace("\\", "/") for member in members}
        if any(
            name.startswith("/") or ".." in Path(name).parts or ":" in name.split("/", 1)[0]
            for name in names
        ):
            raise RuntimeError("unsafe recovery member path")
        if any(_is_special(member) for member in members):
            raise RuntimeError("recovery ZIP contains a link or special member")
        manifest = json.loads(archive.read("service/manifest.json").decode("utf-8"))
        if manifest.get("schema") != 1 or manifest.get("application_id") != "fedorinov-rewards-recovery":
            raise RuntimeError("invalid recovery manifest identity")
        version = str(manifest.get("version") or "")
        if version not in SUPPORTED_SOURCE_VERSIONS:
            raise RuntimeError("unsupported recovery version contract")
        expected = expected_root_files(version) | expected_service_files(version)
        if names != expected:
            raise RuntimeError(f"unexpected recovery members: {sorted(names ^ expected)}")
        if manifest.get("supported_source_versions") != SUPPORTED_SOURCE_VERSIONS[version]:
            raise RuntimeError("invalid recovery version contract")
        nested_bytes = archive.read(f"service/FedorinovRewards_WebPreview_v{version}.zip")
        if len(nested_bytes) != int(manifest["package_size"]):
            raise RuntimeError("nested main package size mismatch")
        if hashlib.sha256(nested_bytes).hexdigest() != manifest["package_sha256"]:
            raise RuntimeError("nested main package checksum mismatch")
        instruction = archive.read("ИНСТРУКЦИЯ.txt").decode("utf-8")
        for expected in (
            "Извлечь всё",
            "отдельную временную папку",
            "Не распаковывайте архив поверх",
            "Старую папку не удаляйте",
            "Базу и фотографии вручную не переносите",
        ):
            if expected not in instruction:
                raise RuntimeError(f"recovery instruction is missing: {expected}")
        if version == "2.0.7":
            _validate_corrective_bootstrap(archive.read("ВОССТАНОВИТЬ_И_ЗАПУСТИТЬ_2.0.7.bat"))

    from io import BytesIO

    with ZipFile(BytesIO(nested_bytes)) as nested:
        validate_zip_members(nested)
        if nested.testzip():
            raise RuntimeError("nested main package is corrupt")
        requirements = nested.read("FedorinovRewards_WebPreview/backend/requirements.txt")
        if hashlib.sha256(requirements).hexdigest() != manifest.get("requirements_sha256"):
            raise RuntimeError("nested requirements checksum mismatch")
        nested_members = len(nested.infolist())
    return {
        "safe": True,
        "members": len(names),
        "nested_members": nested_members,
        "nested_sha256": manifest["package_sha256"],
        "recovery_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python3 scripts/check_recovery_package_safety.py <recovery-zip>", file=sys.stderr)
        return 2
    path = Path(argv[1]).expanduser().resolve(strict=False)
    try:
        result = check_recovery_package(path)
    except (BadZipFile, KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"recovery package safety failed: {exc}", file=sys.stderr)
        return 1
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
