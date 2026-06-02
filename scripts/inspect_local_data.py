#!/usr/bin/env python3
from pathlib import Path
import os
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = Path("/Users/hermes/Desktop/Rewards")
TABLES_TO_COUNT = [
    "person",
    "rewards",
    "mark",
    "guide",
    "guide_lev_0",
    "guide_lev_1",
    "guide_lev_2",
    "guide_lev_3",
    "guide_lev_4",
]


def load_env_file() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def data_dir() -> Path:
    return Path(os.path.expandvars(os.getenv("REWARDS_DATA_DIR", str(DEFAULT_DATA_DIR)))).expanduser()


def db_path(base_dir: Path) -> Path:
    configured = os.getenv("REWARDS_DB_PATH")
    if configured:
        return Path(os.path.expandvars(configured)).expanduser()
    return base_dir / "database" / "MyDatabase.sqlite"


def connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def main() -> int:
    load_env_file()
    base_dir = data_dir()
    database = db_path(base_dir)

    print(f"data_dir_exists: {base_dir.exists()}")
    print(f"database_exists: {database.exists()}")
    print("read_only: true")

    if not database.exists():
        print(f"error: database not found at {database}")
        return 1

    with connect_readonly(database) as connection:
        rows = connection.execute(
            "select name from sqlite_master where type = 'table' order by name"
        ).fetchall()
        tables = [row["name"] for row in rows]

        print("tables:")
        for table in tables:
            print(f"- {table}")

        print("counts:")
        existing = set(tables)
        for table in TABLES_TO_COUNT:
            if table not in existing:
                print(f"- {table}: missing")
                continue
            count = connection.execute(f'select count(*) as count from "{table}"').fetchone()["count"]
            print(f"- {table}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
