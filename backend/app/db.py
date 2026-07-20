from pathlib import Path
import sqlite3


def _configure_connection(connection: sqlite3.Connection) -> sqlite3.Connection:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def open_readonly_connection(db_path: Path) -> sqlite3.Connection:
    """Open SQLite in read-only mode. Callers must not execute write statements."""
    resolved = db_path.resolve()
    uri = f"file:{resolved}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    return _configure_connection(connection)


def open_write_connection(db_path: Path, write_mode: bool) -> sqlite3.Connection:
    """Open SQLite for write routes while editing is enabled."""
    if not write_mode:
        raise PermissionError("Редактирование выключено.")
    connection = sqlite3.connect(db_path.resolve())
    return _configure_connection(connection)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}
