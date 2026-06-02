#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import os
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_ROOT = Path.home() / "LocalData" / "FedorinovRewards" / "backups"
REQUIRED_ITEMS = [
    Path("database") / "MyDatabase.sqlite",
    Path("Source"),
    Path("SourceMark"),
    Path("default"),
]


def _load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _data_root() -> Path:
    _load_dotenv()
    value = os.getenv("REWARDS_DATA_DIR", "").strip()
    if not value:
        raise RuntimeError("REWARDS_DATA_DIR is not configured")
    return Path(os.path.expandvars(value)).expanduser().resolve()


def _validate(root: Path) -> None:
    if not root.exists() or not root.is_dir():
        raise RuntimeError(f"REWARDS_DATA_DIR does not exist or is not a directory: {root}")
    for item in REQUIRED_ITEMS:
        path = root / item
        if not path.exists():
            raise RuntimeError(f"Required backup item is missing: {path}")


def _iter_backup_files(root: Path):
    for relative in (Path("database"), Path("Source"), Path("SourceMark"), Path("default")):
        path = root / relative
        if path.is_file():
            yield path, Path("Rewards") / relative
            continue
        for child in sorted(path.rglob("*")):
            if child.is_file():
                yield child, Path("Rewards") / child.relative_to(root)


def main() -> int:
    try:
        root = _data_root()
        _validate(root)
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = BACKUP_ROOT / f"Rewards_backup_{timestamp}.zip"

        file_count = 0
        with ZipFile(backup_path, "w", compression=ZIP_DEFLATED) as archive:
            for source, archive_name in _iter_backup_files(root):
                archive.write(source, archive_name)
                file_count += 1

        size = backup_path.stat().st_size
        print(f"path: {backup_path}")
        print(f"size_bytes: {size}")
        print(f"files: {file_count}")
        return 0
    except Exception as exc:
        print(f"backup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
