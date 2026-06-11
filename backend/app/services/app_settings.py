from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from ..config import Settings
from ..version import APP_NAME


PROGRAM_TITLE_KEY = "program_title"
MAX_PROGRAM_TITLE_LENGTH = 160


class AppSettingsError(ValueError):
    pass


def app_settings_path(settings: Settings) -> Path:
    return settings.rewards_data_dir / "app_settings.json"


def load_app_settings(settings: Settings) -> dict[str, object]:
    path = app_settings_path(settings)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def program_title(settings: Settings) -> str:
    payload = load_app_settings(settings)
    if PROGRAM_TITLE_KEY not in payload:
        return APP_NAME
    return str(payload.get(PROGRAM_TITLE_KEY) or "")


def normalize_program_title(value: object) -> str:
    title = str(value or "").strip()
    if len(title) > MAX_PROGRAM_TITLE_LENGTH:
        raise AppSettingsError("Название программы слишком длинное.")
    return title


def save_program_title(settings: Settings, value: object) -> str:
    title = normalize_program_title(value)
    path = app_settings_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = load_app_settings(settings)
    payload[PROGRAM_TITLE_KEY] = title

    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp_file:
        json.dump(payload, tmp_file, ensure_ascii=False, indent=2)
        tmp_file.write("\n")
        tmp_path = Path(tmp_file.name)
    tmp_path.replace(path)
    return title
