#!/usr/bin/env python3
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import argparse
import os
import sqlite3
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MigrationBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class MigrationSettings:
    rewards_data_dir: Path
    rewards_db_path: Path
    write_mode: bool
    require_backup_before_write: bool


def _load_local_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env_path(name: str, default: str | None = None) -> Path:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return Path(os.path.expandvars(value)).expanduser()


def _settings() -> MigrationSettings:
    _load_local_env()
    data_dir = _env_path("REWARDS_DATA_DIR", "/Users/hermes/Desktop/Rewards")
    db_path = _env_path("REWARDS_DB_PATH", str(data_dir / "database" / "MyDatabase.sqlite"))
    return MigrationSettings(
        rewards_data_dir=data_dir,
        rewards_db_path=db_path,
        write_mode=os.getenv("WRITE_MODE", "false").lower() == "true",
        require_backup_before_write=os.getenv("REQUIRE_BACKUP_BEFORE_WRITE", "true").lower() == "true",
    )


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    resolved = db_path.resolve()
    connection = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _open_write(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path.resolve())
    connection.row_factory = sqlite3.Row
    connection.execute("pragma foreign_keys=on")
    connection.execute("pragma busy_timeout=5000")
    return connection


def _backup_dir_for_data_root(data_dir: Path) -> Path:
    return data_dir.expanduser().resolve().parent / "backups"


def _recent_backup_exists(data_dir: Path, max_age_hours: int = 24) -> bool:
    backup_dir = _backup_dir_for_data_root(data_dir)
    if not backup_dir.exists() or not backup_dir.is_dir():
        return False
    cutoff = datetime.now().timestamp() - timedelta(hours=max_age_hours).total_seconds()
    return any(path.is_file() and path.stat().st_mtime >= cutoff for path in backup_dir.glob("Rewards_backup_*.zip"))


def _ensure_write_allowed(settings: MigrationSettings) -> None:
    if not settings.write_mode:
        raise MigrationBlockedError("WRITE_MODE=true is required for migration")
    if settings.require_backup_before_write and not _recent_backup_exists(settings.rewards_data_dir):
        raise MigrationBlockedError("Create a fresh backup before migration")


def biography_column_exists(db_path: Path) -> bool:
    with closing(_open_readonly(db_path)) as connection:
        columns = {row["name"] for row in connection.execute("pragma table_info(person)").fetchall()}
    return "biography" in columns


def apply_migration() -> str:
    settings = _settings()
    _ensure_write_allowed(settings)
    if biography_column_exists(settings.rewards_db_path):
        return "already_exists"
    with closing(_open_write(settings.rewards_db_path)) as connection:
        connection.execute("alter table person add column biography text")
        connection.commit()
    return "added"


def dry_run() -> str:
    settings = _settings()
    exists = biography_column_exists(settings.rewards_db_path)
    print(f"database: {settings.rewards_db_path}")
    print(f"biography_exists: {str(exists).lower()}")
    print(f"action: {'noop' if exists else 'add_column'}")
    return "already_exists" if exists else "would_add"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add person.biography column safely.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Show migration status without changing SQLite.")
    group.add_argument("--apply", action="store_true", help="Apply migration. Requires WRITE_MODE=true and fresh backup.")
    args = parser.parse_args(argv)

    try:
        if args.dry_run:
            dry_run()
            return 0
        result = apply_migration()
        print(f"migration_result: {result}")
        return 0
    except MigrationBlockedError as exc:
        print(f"migration blocked: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
