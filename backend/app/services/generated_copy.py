from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import secrets
import subprocess
import tempfile
import time
from typing import Callable


OPEN_COPY_HEADER = "X-Fedorinov-Open-Copy-Token"
OPEN_COPY_TTL_SECONDS = 24 * 60 * 60
_TOKEN_PATTERN = re.compile(r"[0-9a-f]{32}")


class GeneratedCopyError(ValueError):
    pass


def generated_copy_root() -> Path:
    return Path(tempfile.gettempdir()) / "FedorinovRewards" / "open-copy"


def stage_generated_pdf(content: bytes, *, root: Path | None = None) -> str:
    target_root = (root or generated_copy_root()).resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_copies(target_root)
    token = secrets.token_hex(16)
    temporary = target_root / f".{token}.tmp"
    target = target_root / f"{token}.pdf"
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return token


def open_generated_pdf(
    token: object,
    *,
    root: Path | None = None,
    opener: Callable[[Path], None] | None = None,
) -> Path:
    clean_token = str(token or "").strip().lower()
    if not _TOKEN_PATTERN.fullmatch(clean_token):
        raise GeneratedCopyError("Некорректная копия PDF.")
    target_root = (root or generated_copy_root()).resolve()
    target = (target_root / f"{clean_token}.pdf").resolve()
    try:
        target.relative_to(target_root)
    except ValueError as exc:
        raise GeneratedCopyError("Некорректная копия PDF.") from exc
    if not target.is_file():
        raise GeneratedCopyError("Копия PDF больше недоступна. Сформируйте файл ещё раз.")
    (opener or _default_opener)(target)
    return target


def _cleanup_stale_copies(root: Path, *, now: float | None = None) -> None:
    threshold = (time.time() if now is None else now) - OPEN_COPY_TTL_SECONDS
    for path in root.glob("*.pdf"):
        try:
            if path.is_file() and path.stat().st_mtime < threshold:
                path.unlink()
        except OSError:
            continue


def _default_opener(path: Path) -> None:
    system = platform.system().lower()
    if system == "windows" and hasattr(os, "startfile"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    if system == "darwin":
        subprocess.Popen(["open", str(path)], close_fds=True)
        return
    subprocess.Popen(["xdg-open", str(path)], close_fds=True)
