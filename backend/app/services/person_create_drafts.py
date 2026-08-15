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
from .media_image_policy import ImagePolicyError, NormalizedImage, normalize_uploaded_image
from .media_filenames import write_collision_safe_media
from .media_lifecycle import discard_uncommitted_image
from .photos import (
    MAX_PHOTO_BYTES,
    PERSON_PHOTO_FIELDS,
    REWARD_PHOTO_FIELDS,
    PhotoValidationError,
)
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


def _normalize_draft_upload(filename: str, content: bytes) -> NormalizedImage:
    if len(content) > MAX_PHOTO_BYTES:
        raise PhotoValidationError("Файл больше 25 MB")
    try:
        return normalize_uploaded_image(filename, content)
    except ImagePolicyError as exc:
        raise PhotoValidationError(str(exc)) from exc


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


def start_reward(settings: Settings, token: object) -> str:
    ensure_write_allowed(settings)
    draft = load_draft(settings, token)
    reward_token = uuid4().hex
    rewards = list(draft["rewards"])
    rewards.append({"token": reward_token, "data": {}, "photos": {}})
    draft["rewards"] = rewards
    _save(settings, draft)
    return reward_token


def _reward_entry(draft: dict[str, object], reward_token: object) -> tuple[int, dict[str, object]]:
    clean_token = _token(reward_token)
    for index, raw in enumerate(draft["rewards"]):
        if isinstance(raw, dict) and raw.get("token") == clean_token:
            return index, raw
    raise ValueError("Награда черновика не найдена.")


def load_reward(settings: Settings, token: object, reward_token: object) -> dict[str, object]:
    draft = load_draft(settings, token)
    _index, entry = _reward_entry(draft, reward_token)
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    photos = entry.get("photos") if isinstance(entry.get("photos"), dict) else {}
    return {"token": entry["token"], "data": data, "photos": photos}


def save_reward(
    settings: Settings,
    token: object,
    reward_token: object,
    values: dict[str, object],
) -> dict[str, object]:
    ensure_write_allowed(settings)
    data = reward_data_from_mapping(values)
    if data.id_name is None:
        raise ValueError("Выберите наименование награды.")
    draft = load_draft(settings, token)
    index, entry = _reward_entry(draft, reward_token)
    for other_index, raw in enumerate(draft["rewards"]):
        if other_index == index or not isinstance(raw, dict):
            continue
        raw_data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        if data.number is not None and (
            int(raw_data.get("id_name") or 0) == data.id_name
            and raw_data.get("number") == data.number
        ):
            raise ValueError("Такая награда с этим номером уже добавлена в черновик.")
    updated = dict(entry)
    updated["data"] = asdict(data)
    updated["complete"] = True
    rewards = list(draft["rewards"])
    rewards[index] = updated
    draft["rewards"] = rewards
    _save(settings, draft)
    return updated


def add_reward(settings: Settings, token: object, values: dict[str, object]) -> dict[str, object]:
    reward_token = start_reward(settings, token)
    save_reward(settings, token, reward_token, values)
    return load_draft(settings, token)


def remove_reward(settings: Settings, token: object, index: int) -> dict[str, object]:
    ensure_write_allowed(settings)
    draft = load_draft(settings, token)
    rewards = list(draft["rewards"])
    if index < 0 or index >= len(rewards):
        raise ValueError("Награда черновика не найдена.")
    removed = rewards.pop(index)
    draft["rewards"] = rewards
    _save(settings, draft)
    if isinstance(removed, dict) and removed.get("token"):
        reward_dir = _draft_dir(settings, token) / "rewards" / _token(removed["token"])
        if reward_dir.is_dir():
            shutil.rmtree(reward_dir)
    return draft


def discard_reward(settings: Settings, token: object, reward_token: object) -> None:
    ensure_write_allowed(settings)
    draft = load_draft(settings, token)
    index, _entry = _reward_entry(draft, reward_token)
    remove_reward(settings, token, index)


def stage_photo(settings: Settings, token: object, photo_field: str, filename: str, content: bytes) -> dict[str, object]:
    ensure_write_allowed(settings)
    field = next((item for item in PERSON_PHOTO_FIELDS if item.field == photo_field), None)
    if field is None:
        raise PhotoValidationError("Некорректное поле фото")
    normalized = _normalize_draft_upload(filename, content)
    draft = load_draft(settings, token)
    photo_dir = _draft_dir(settings, token) / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    for old in photo_dir.glob(f"{photo_field}.*"):
        old.unlink()
    target = photo_dir / f"{photo_field}{normalized.extension}"
    target.write_bytes(normalized.content)
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


def stage_reward_photo(
    settings: Settings,
    token: object,
    reward_token: object,
    photo_field: str,
    filename: str,
    content: bytes,
) -> dict[str, object]:
    ensure_write_allowed(settings)
    field = next((item for item in REWARD_PHOTO_FIELDS if item.field == photo_field), None)
    if field is None:
        raise PhotoValidationError("Некорректное поле фото")
    normalized = _normalize_draft_upload(filename, content)
    draft = load_draft(settings, token)
    index, entry = _reward_entry(draft, reward_token)
    photo_dir = _draft_dir(settings, token) / "rewards" / _token(reward_token) / "photos"
    photo_dir.mkdir(parents=True, exist_ok=True)
    for old in photo_dir.glob(f"{photo_field}.*"):
        old.unlink()
    target = photo_dir / f"{photo_field}{normalized.extension}"
    target.write_bytes(normalized.content)
    updated = dict(entry)
    photos = dict(updated.get("photos") or {})
    photos[photo_field] = {"filename": target.name, "original_name": Path(filename).name}
    updated["photos"] = photos
    rewards = list(draft["rewards"])
    rewards[index] = updated
    draft["rewards"] = rewards
    _save(settings, draft)
    return updated


def staged_reward_photo_path(
    settings: Settings,
    token: object,
    reward_token: object,
    photo_field: str,
) -> Path | None:
    reward = load_reward(settings, token, reward_token)
    item = reward["photos"].get(photo_field)
    if not isinstance(item, dict):
        return None
    filename = Path(str(item.get("filename") or "")).name
    path = _draft_dir(settings, token) / "rewards" / _token(reward_token) / "photos" / filename
    return path if filename and path.is_file() else None


def clear_staged_reward_photo(
    settings: Settings,
    token: object,
    reward_token: object,
    photo_field: str,
) -> None:
    ensure_write_allowed(settings)
    draft = load_draft(settings, token)
    index, entry = _reward_entry(draft, reward_token)
    path = staged_reward_photo_path(settings, token, reward_token, photo_field)
    if path is not None:
        path.unlink()
    updated = dict(entry)
    photos = dict(updated.get("photos") or {})
    photos.pop(photo_field, None)
    updated["photos"] = photos
    rewards = list(draft["rewards"])
    rewards[index] = updated
    draft["rewards"] = rewards
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
                if not isinstance(raw, dict):
                    continue
                reward_data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
                if not reward_data.get("id_name"):
                    continue
                reward_id = create_reward_in_connection(connection, person_id, RewardWriteData(**reward_data))
                reward_token = raw.get("token")
                for field in REWARD_PHOTO_FIELDS:
                    if not reward_token:
                        continue
                    source = staged_reward_photo_path(settings, token, reward_token, field.field)
                    if source is None:
                        continue
                    relative_dir = Path("Source") / str(person_id) / str(reward_id)
                    target = write_collision_safe_media(
                        settings.rewards_data_dir / relative_dir,
                        field.stem,
                        source.suffix.lower(),
                        source.read_bytes(),
                    )
                    relative = (relative_dir / target.name).as_posix()
                    written_paths.append(relative)
                    connection.execute(
                        f"update rewards set {field.field} = ? where id = ?",
                        (relative, reward_id),
                    )
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
