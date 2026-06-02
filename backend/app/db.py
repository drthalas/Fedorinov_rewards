from pathlib import Path
import sqlite3


def open_readonly_connection(db_path: Path) -> sqlite3.Connection:
    """Open SQLite in read-only mode. Callers must not execute write statements."""
    resolved = db_path.resolve()
    uri = f"file:{resolved}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection
