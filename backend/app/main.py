from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .config import get_settings
from .db import open_readonly_connection


app = FastAPI(title="Fedorinov Rewards", version="0.1.0")


@app.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    db_readable = False

    if settings.db_exists:
        try:
            with open_readonly_connection(settings.rewards_db_path) as connection:
                connection.execute("select 1").fetchone()
            db_readable = True
        except Exception:
            db_readable = False

    return {
        "status": "ok" if settings.data_dir_exists and settings.db_exists and db_readable else "warning",
        "read_only": settings.read_only,
        "data_dir_exists": settings.data_dir_exists,
        "db_exists": settings.db_exists,
        "db_readable": db_readable,
        "errors": settings.validation_errors(),
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    settings = get_settings()
    errors = settings.validation_errors()
    error_items = "".join(f"<li>{error}</li>" for error in errors) or "<li>No configuration errors detected.</li>"

    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <title>Fedorinov Rewards</title>
        <style>
          body {{
            font-family: Arial, sans-serif;
            max-width: 860px;
            margin: 48px auto;
            line-height: 1.5;
            color: #1f2933;
          }}
          code {{
            background: #f1f5f9;
            padding: 2px 5px;
          }}
        </style>
      </head>
      <body>
        <h1>Fedorinov Rewards</h1>
        <p>Read-only modernization skeleton for the legacy Rewards application.</p>
        <h2>Configuration</h2>
        <ul>
          <li>Data directory: <code>{settings.rewards_data_dir}</code></li>
          <li>Database: <code>{settings.rewards_db_path}</code></li>
          <li>Read-only: <code>{settings.read_only}</code></li>
        </ul>
        <h2>Health</h2>
        <ul>{error_items}</ul>
      </body>
    </html>
    """
