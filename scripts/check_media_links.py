#!/usr/bin/env python3
from pathlib import Path
import hashlib
import os
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = Path("/Users/hermes/Desktop/Rewards")
MEDIA_DIRS = ("Source", "SourceMark", "default")
PATH_COLUMN_HINTS = (
    "foto",
    "photo",
    "image",
    "img",
    "file",
    "path",
    "source",
    "mark",
    "picture",
)
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff")


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


def table_names(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "select name from sqlite_master where type = 'table' order by name"
    ).fetchall()
    return [row["name"] for row in rows]


def candidate_columns(connection: sqlite3.Connection, table: str) -> list[str]:
    columns = connection.execute(f'pragma table_info("{table}")').fetchall()
    candidates: list[str] = []
    for column in columns:
        name = column["name"]
        lowered = name.lower()
        if any(hint in lowered for hint in PATH_COLUMN_HINTS):
            candidates.append(name)
    return candidates


def looks_like_media_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    return lowered.endswith(IMAGE_SUFFIXES) or any(
        lowered.startswith(f"{folder.lower()}/") or lowered.startswith(f"{folder.lower()}\\")
        for folder in MEDIA_DIRS
    )


def resolve_media_path(base_dir: Path, raw_value: str) -> Path:
    normalized = raw_value.strip().replace("\\", "/")
    candidate = Path(normalized)
    if candidate.is_absolute():
        return candidate

    for folder in MEDIA_DIRS:
        if normalized.lower().startswith(f"{folder.lower()}/"):
            return base_dir / normalized

    return base_dir / "Source" / normalized


def safe_path_label(base_dir: Path, path: Path) -> str:
    try:
        relative = path.relative_to(base_dir)
    except ValueError:
        relative = Path(path.name)

    digest = hashlib.sha256(str(relative).encode("utf-8")).hexdigest()[:12]
    parts = list(relative.parts)
    if not parts:
        return f"<redacted:{digest}>"
    parts[-1] = f"<redacted:{digest}{Path(parts[-1]).suffix.lower()}>"
    return str(Path(*parts))


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

    total_paths = 0
    existing = 0
    missing = 0
    missing_labels: list[str] = []
    inspected_columns: list[str] = []

    with connect_readonly(database) as connection:
        for table in table_names(connection):
            columns = candidate_columns(connection, table)
            for column in columns:
                inspected_columns.append(f"{table}.{column}")
                rows = connection.execute(
                    f'select "{column}" as media_path from "{table}" where "{column}" is not null'
                ).fetchall()
                for row in rows:
                    raw_value = row["media_path"]
                    if not looks_like_media_path(raw_value):
                        continue
                    total_paths += 1
                    resolved = resolve_media_path(base_dir, raw_value)
                    if resolved.exists() and resolved.is_file():
                        existing += 1
                    else:
                        missing += 1
                        if len(missing_labels) < 20:
                            missing_labels.append(safe_path_label(base_dir, resolved))

    print("inspected_columns:")
    for column in inspected_columns:
        print(f"- {column}")
    print(f"total paths: {total_paths}")
    print(f"existing: {existing}")
    print(f"missing: {missing}")
    print("first 20 missing paths:")
    for label in missing_labels:
        print(f"- {label}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
