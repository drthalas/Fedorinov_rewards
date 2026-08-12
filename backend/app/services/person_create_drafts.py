from __future__ import annotations

from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
from uuid import uuid4

from ..config import Settings
from ..db import open_write_connection
from ..repositories.persons_write import PersonWriteData, create_person_in_connection
from ..repositories.rewards_write import RewardWriteData, create_reward_in_connection, reward_data_from_mapping
from .audit import log_action
from .media_filenames import write_collision_safe_media
from .media_lifecycle import discard_uncommitted_image
from .photos import MAX_PHOTO_BYTES, PERSON_PHOTO_FIELDS, PhotoValidationError, _extension, _matches_image_signature
from .write_guard import ensure_write_allowed


DRAFT_TTL = timedelta(hours=24)
TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def new_draft_token() -> str:
    return uuid4().hex


def _token(value: object) -> str:
    token = str(value or "").strip().lower()
    if not TOKEN_PATTERN.fullmatch(token):
        raise ValueError("Некорректный черновик создания.")
    return token


def _root(settings: Settings) -> Path:
    return settings.rewards_data_dir / ".fedorinov-create-drafts"


def _draft_dir(settings: Settings, token: object) -> Path:
    return _root(settings) / _token(token)


def cleanup_expired_drafts(settings: Settings) -> int:
    root = _root(settings)
    if not root.is_dir():
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - DRAFT_TTL.total_seconds()
    removed = 0
    for path in root.iterdir():
        if path.is_dir() and path.stat().st_mtime < cutoff:
            shutil.rmtree(path)
            removed += 1
    return removed


def load_draft(settings: Settings, token: object) -> dict[str, object]:
    token = _token(token)
    path = _draft_dir(settings, token) / "draft.json"
    if not path.is_file():
        return {"token": token, "person": {}, "rewards": [], "photos": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    return {
        "token": token,
        "person": payload.get("person") if isinstance(payload.get("person"), dict) else {},
        "rewards": payload.get("rewards") if isinstance(payload.get("rewards"), list) else [],
        "photos": payload.get("photos") if isinstance(payload.get("photos"), dict) else {},
    }


def _save(settings: Settings, draft: dict[str, object]) -> None:
    directory = _draft_dir(settings, draft["token"])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "draft.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(draft, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def save_person_values(settings: Settings, token: object, values: dict[str, object]) -> dict[str, object]:
    ensure_write_allowed(settings)
    draft = load_draft(settings, token)
    allowed = ("fio", "birthday", "id_rank", "link1", "link2", "comment", "biography", "return_to")
    draft["person"] = {key: str(values.get(key) or "") for key in allowed}
    _save(settings, draft)
    return draft


def add_reward(settings: Settings, token: object, values: dict[str, object]) -> dict[str, object]:
    ensure_write_allowed(settings)
    data = reward_data_from_mapping(values)
    if data.id_name is None:
        raise ValueError("Выберите наименование награды.")
    draft = load_draft(settings, token)
    rewards = list(draft["rewards"])
    if data.number is not None and any(
        int(item.get("id_name") or 0) == data.id_name and item.get("number") == data.number for item in rewards
    ):
        raise ValueError("Такая награда с этим номером уже добавлена в черновик.")
    rewards.append(asdict(data))
    draft["rewards"] = rewards
    _save(settings, draft)
    return draft


def remove_reward(settings: Settings, token: object, index: int) -> dict[str, object]:
    ensure_write_allowed(settings)
    draft = load_draft(settings, token)
    rewards = list(draft["rewards"])
    if index < 0 or index >= len(rewards):
        raise ValueError("Награда черновика не найдена.")
    rewards.pop(index)
    draft["rewards"] = rewards
    _save(settings, draft)
    return draft


def stage_photo(settings: Settings, token: object, photo_field: str, filename: str, content: bytes) -> dict[str, object]:
    ensure_write_allowed(settings)
    field = next((item for item in PERSON_PHOTO_FIELDS if item.field == photo_field), None)
    if field is None:
        raise PhotoValidationError("Некорректное поле фото")
    extension = _extension(filename)
    if not content:
        raise PhotoValidationError("Файл пустой")
    if len(content) > MAX_PHOTO_BYTES:
        raise PhotoValidationError("Файл больше 25 MB")
    if not _matches_image_signature(extension, content):
        raise PhotoValidationError("Файл не является корректным изображением выбранного типа")
    draft = load_draft(settings, token)
    photo_dir = _draft_dir(settings, token) / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    for old in photo_dir.glob(f"{photo_field}.*"):
        old.unlink()
    target = photo_dir / f"{photo_field}{extension}"
    target.write_bytes(content)
    photos = dict(draft["photos"])
    photos[photo_field] = {"filename": target.name, "original_name": Path(filename).name}
    draft["photos"] = photos
    _save(settings, draft)
    return draft


def staged_photo_path(settings: Settings, token: object, photo_field: str) -> Path | None:
    draft = load_draft(settings, token)
    item = draft["photos"].get(photo_field)
    if not isinstance(item, dict):
        return None
    filename = Path(str(item.get("filename") or "")).name
    path = _draft_dir(settings, token) / "photos" / filename
    return path if filename and path.is_file() else None


def clear_staged_photo(settings: Settings, token: object, photo_field: str) -> None:
    ensure_write_allowed(settings)
    draft = load_draft(settings, token)
    path = staged_photo_path(settings, token, photo_field)
    if path is not None:
        path.unlink()
    photos = dict(draft["photos"])
    photos.pop(photo_field, None)
    draft["photos"] = photos
    _save(settings, draft)


def discard_draft(settings: Settings, token: object) -> None:
    directory = _draft_dir(settings, token)
    if directory.is_dir():
        shutil.rmtree(directory)


def commit_draft(settings: Settings, token: object, person_data: PersonWriteData) -> int:
    ensure_write_allowed(settings)
    draft = load_draft(settings, token)
    written_paths: list[str] = []
    created_folder: Path | None = None
    with closing(open_write_connection(settings.rewards_db_path, settings.write_mode)) as connection:
        connection.execute("begin immediate")
        try:
            person_id, created_folder, _fields = create_person_in_connection(connection, settings, person_data)
            for field in PERSON_PHOTO_FIELDS:
                source = staged_photo_path(settings, token, field.field)
                if source is None:
                    continue
                target_dir = settings.rewards_data_dir / "Source" / str(person_id)
                target = write_collision_safe_media(target_dir, field.stem, source.suffix.lower(), source.read_bytes())
                relative = (Path("Source") / str(person_id) / target.name).as_posix()
                written_paths.append(relative)
                connection.execute(f"update person set {field.field} = ? where id = ?", (relative, person_id))
            for raw in draft["rewards"]:
                create_reward_in_connection(connection, person_id, RewardWriteData(**raw))
            connection.commit()
        except Exception:
            connection.rollback()
            for relative in written_paths:
                discard_uncommitted_image(settings, relative, allowed_roots={"Source"})
            if created_folder is not None:
                try:
                    created_folder.rmdir()
                except OSError:
                    pass
            raise
    discard_draft(settings, token)
    log_action("create", "person", person_id, {"draft": True, "rewards": len(draft["rewards"]), "photos": len(written_paths)})
    return person_id
