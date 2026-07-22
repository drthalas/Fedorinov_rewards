#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from zipfile import ZipFile


BROKEN_RECOVERY_SHA256 = "4c0f858f9bdb3b082584e15ac4fc7cc1eca58ea29e49cf8ce82340b708586415"
BROKEN_BAT = "ВОССТАНОВИТЬ_И_ЗАПУСТИТЬ_2.0.6.bat"
CORRECTIVE_BAT = "ВОССТАНОВИТЬ_И_ЗАПУСТИТЬ_2.0.7.bat"
CMD_ERROR_MARKER = b"is not recognized as an internal or external command"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _safe_extract(zip_path: Path, destination: Path) -> None:
    with ZipFile(zip_path) as archive:
        for member in archive.infolist():
            parts = tuple(part for part in member.filename.replace("\\", "/").split("/") if part)
            if not parts or ".." in parts or parts[0].endswith(":"):
                raise RuntimeError(f"unsafe recovery member: {member.filename}")
        archive.extractall(destination)


def _bat_metadata(content: bytes) -> dict[str, object]:
    return {
        "bytes": len(content),
        "sha256": sha256_bytes(content),
        "bom": (
            "utf-8"
            if content.startswith(b"\xef\xbb\xbf")
            else "utf-16-le"
            if content.startswith(b"\xff\xfe")
            else "utf-16-be"
            if content.startswith(b"\xfe\xff")
            else "none"
        ),
        "ascii_only": content.isascii(),
        "crlf": content.count(b"\r\n"),
        "lf": content.count(b"\n"),
        "bare_lf": content.replace(b"\r\n", b"").count(b"\n"),
        "bare_cr": content.replace(b"\r\n", b"").count(b"\r"),
    }


def _probe_helper(path: Path, marker: Path) -> None:
    path.write_text(
        "from pathlib import Path\n"
        "import os\n"
        "Path(os.environ['RECOVERY_BOOTSTRAP_MARKER']).write_text('helper reached\\n', encoding='utf-8')\n",
        encoding="ascii",
    )
    marker.unlink(missing_ok=True)


def _run_cmd_batch(batch: Path, marker: Path, *, codepage: int, shell_association: bool) -> dict[str, object]:
    if os.name != "nt":
        raise RuntimeError("native cmd.exe gate requires Windows")
    wrapper = marker.parent / ("shell-association.cmd" if shell_association else "direct-call.cmd")
    command = 'start "" "%TARGET_BAT%"' if shell_association else 'call "%TARGET_BAT%"'
    wrapper.write_bytes(
        (
            "@echo off\r\n"
            f"chcp {codepage} >nul\r\n"
            f"{command}\r\n"
            "exit /b %ERRORLEVEL%\r\n"
        ).encode("ascii")
    )
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONUTF8": "1",
            "RECOVERY_BOOTSTRAP_MARKER": str(marker),
            "TARGET_BAT": str(batch),
        }
    )
    output_path = marker.with_suffix(".cmd-output.bin")
    timed_out = False
    with output_path.open("wb") as output_handle:
        process = subprocess.Popen(
            ["cmd.exe", "/d", "/c", str(wrapper)],
            stdin=subprocess.PIPE,
            stdout=output_handle,
            stderr=subprocess.STDOUT,
            env=environment,
        )
        try:
            process.communicate(input=b"\r\n" * 32, timeout=20)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                check=False,
            )
            process.wait(timeout=10)
    output = output_path.read_bytes()
    if shell_association and not marker.is_file():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not marker.is_file():
            time.sleep(0.1)
        timed_out = not marker.is_file()
    decoded: dict[str, str] = {}
    for encoding in ("utf-8", "cp866", "cp1251"):
        decoded[encoding] = output.decode(encoding, errors="replace")[-6000:]
    return {
        "codepage": codepage,
        "mode": "shell-association" if shell_association else "cmd-call",
        "returncode": process.returncode,
        "timed_out": timed_out,
        "helper_reached": marker.is_file(),
        "cmd_parser_error": CMD_ERROR_MARKER in output,
        "output_sha256": sha256_bytes(output),
        "output_hex_tail": output[-1200:].hex(),
        "decoded_tail": decoded,
    }


def inspect_public_failure(public_recovery: Path, root: Path) -> dict[str, object]:
    public_bytes = public_recovery.read_bytes()
    if sha256_bytes(public_bytes) != BROKEN_RECOVERY_SHA256:
        raise RuntimeError("public v2.0.6 recovery checksum mismatch")
    destination = root / "Desktop" / "Проверка сломанного recovery с пробелами"
    destination.mkdir(parents=True)
    _safe_extract(public_recovery, destination)
    batch = destination / BROKEN_BAT
    helper = destination / "service" / "recovery_v206.py"
    marker = root / "broken-helper-reached.txt"
    metadata = _bat_metadata(batch.read_bytes())
    _probe_helper(helper, marker)
    execution = _run_cmd_batch(batch, marker, codepage=866, shell_association=False)
    return {
        "recovery_sha256": sha256_bytes(public_bytes),
        "batch": metadata,
        "execution": execution,
        "mutation_boundary": "helper-not-reached" if not execution["helper_reached"] else "helper-reached",
    }


def verify_corrective_bootstrap(recovery: Path, root: Path) -> dict[str, object]:
    scenarios: list[dict[str, object]] = []
    locations = (
        root / "Путь с пробелами" / "Восстановление",
        root / "Desktop" / "Recovery для Сергея",
        root / "Downloads" / "Архив восстановления",
    )
    for location in locations:
        location.mkdir(parents=True)
        _safe_extract(recovery, location)
        batch = location / CORRECTIVE_BAT
        helper = location / "service" / "recovery_v207.py"
        metadata = _bat_metadata(batch.read_bytes())
        if not metadata["ascii_only"] or metadata["bare_lf"] or metadata["bare_cr"]:
            raise RuntimeError(f"corrective bootstrap encoding contract failed: {metadata}")
        for codepage in (866, 1251, 65001):
            marker = root / f"corrective-{len(scenarios)}.txt"
            _probe_helper(helper, marker)
            result = _run_cmd_batch(batch, marker, codepage=codepage, shell_association=False)
            result["path"] = str(location)
            result["batch"] = metadata
            if (
                result["timed_out"]
                or result["returncode"] != 0
                or not result["helper_reached"]
                or result["cmd_parser_error"]
            ):
                raise RuntimeError(f"corrective cmd bootstrap failed: {result}")
            scenarios.append(result)

        marker = root / f"corrective-shell-{len(scenarios)}.txt"
        _probe_helper(helper, marker)
        result = _run_cmd_batch(batch, marker, codepage=866, shell_association=True)
        result["path"] = str(location)
        result["batch"] = metadata
        if (
            result["timed_out"]
            or result["returncode"] != 0
            or not result["helper_reached"]
            or result["cmd_parser_error"]
        ):
            raise RuntimeError(f"corrective shell-association bootstrap failed: {result}")
        scenarios.append(result)
    return {"scenarios": scenarios, "passes": len(scenarios)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run native Windows cmd.exe recovery bootstrap gates.")
    parser.add_argument("--public-v206-recovery", required=True, type=Path)
    parser.add_argument("--corrective-recovery", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("this gate must run under native Windows cmd.exe")
    windows_version = sys.getwindowsversion()
    with tempfile.TemporaryDirectory(prefix="ale327-windows-cmd-") as tmpdir:
        root = Path(tmpdir)
        evidence: dict[str, object] = {
            "platform": sys.platform,
            "windows_version": {
                "major": windows_version.major,
                "minor": windows_version.minor,
                "build": windows_version.build,
                "platform": windows_version.platform,
                "service_pack": windows_version.service_pack,
            },
        }
        evidence["public_v206"] = inspect_public_failure(args.public_v206_recovery, root / "forensic")
        if args.output:
            args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        evidence["corrective_v207"] = verify_corrective_bootstrap(
            args.corrective_recovery,
            root / "corrective",
        )
    rendered = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
