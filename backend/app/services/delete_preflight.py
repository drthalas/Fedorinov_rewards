from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from threading import Lock
import time
from uuid import uuid4

from ..config import Settings
from .deletion_lifecycle import DeletionLifecycleError, recorded_delete_plan


DELETE_PREFLIGHT_TTL_SECONDS = 120


class DeletePreflightError(ValueError):
    pass


class DeletePreflightNotFoundError(DeletePreflightError):
    pass


class DeletePreflightValidationError(DeletePreflightError):
    pass


@dataclass(frozen=True)
class DeletePreflightSnapshot:
    entity_type: str
    entity_id: int
    counts: tuple[tuple[str, int], ...]
    blocking_reason: str | None
    message: str

    @property
    def allowed(self) -> bool:
        return self.blocking_reason is None

    @property
    def fingerprint(self) -> str:
        payload = {
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "counts": dict(self.counts),
            "blocking_reason": self.blocking_reason,
            "message": self.message,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class DeletePreflightGrant:
    operation_id: str
    entity_type: str
    entity_id: int
    fingerprint: str
    allowed: bool
    expires_at: float


_GRANTS: dict[str, DeletePreflightGrant] = {}
_GRANTS_LOCK = Lock()


def _media_counts(media) -> tuple[tuple[str, int], ...]:
    return (
        ("linked_media", int(media.linked_media_count)),
        ("folder_items", int(media.folder_item_count)),
        ("preserved_shared_media", int(media.preserved_shared_reference_count)),
    )


def _snapshot(settings: Settings, entity_type: str, entity_id: int) -> DeletePreflightSnapshot:
    normalized_type = str(entity_type or "").strip().lower()
    technical_id = int(entity_id)
    try:
        if normalized_type == "person":
            from ..repositories.persons_write import person_delete_confirmation_message, person_delete_preview

            preview = person_delete_preview(settings, technical_id)
            counts = (
                ("rewards", int(preview.reward_count)),
                ("person_media", int(preview.person_media_count)),
                ("linked_media", int(preview.database_media_reference_count)),
                ("folder_items", int(preview.folder_item_count)),
                ("preserved_shared_media", int(preview.preserved_shared_reference_count)),
            )
            return DeletePreflightSnapshot(
                normalized_type,
                technical_id,
                counts,
                preview.block_reason,
                person_delete_confirmation_message(preview),
            )
        if normalized_type == "reward":
            from ..repositories.rewards_write import reward_delete_confirmation_message, reward_delete_preview

            preview = reward_delete_preview(settings, technical_id)
            return DeletePreflightSnapshot(
                normalized_type,
                technical_id,
                _media_counts(preview.media),
                preview.media.block_reason,
                reward_delete_confirmation_message(preview),
            )
        if normalized_type == "mark":
            from ..repositories.marks_write import mark_delete_confirmation_message, mark_delete_preview

            preview = mark_delete_preview(settings, technical_id)
            return DeletePreflightSnapshot(
                normalized_type,
                technical_id,
                _media_counts(preview.media),
                preview.media.block_reason,
                mark_delete_confirmation_message(preview),
            )
        if normalized_type == "rank":
            from ..repositories.guides_write import rank_delete_confirmation_message, rank_delete_preview

            preview = rank_delete_preview(settings, technical_id)
            blocking_reason = (
                f"звание используется в карточках кавалеров ({preview.used_count})"
                if preview.used_count
                else preview.media.block_reason
            )
            return DeletePreflightSnapshot(
                normalized_type,
                technical_id,
                (("person_references", int(preview.used_count)), *_media_counts(preview.media)),
                blocking_reason,
                rank_delete_confirmation_message(preview),
            )
        if normalized_type.startswith("guide_level_"):
            from ..repositories.guides_write import guide_delete_confirmation_message, guide_delete_preview

            level = int(normalized_type.removeprefix("guide_level_"))
            preview = guide_delete_preview(settings, level, technical_id)
            if preview.child_count:
                blocking_reason = f"у элемента есть дочерние записи ({preview.child_count})"
            elif preview.usage_count:
                blocking_reason = f"значение используется в наградах или знаках ({preview.usage_count})"
            else:
                blocking_reason = preview.media.block_reason
            return DeletePreflightSnapshot(
                normalized_type,
                technical_id,
                (
                    ("children", int(preview.child_count)),
                    ("usage_references", int(preview.usage_count)),
                    *_media_counts(preview.media),
                ),
                blocking_reason,
                guide_delete_confirmation_message(preview),
            )
    except (ValueError, RuntimeError) as exc:
        if isinstance(exc, DeletePreflightError):
            raise
        raise DeletePreflightNotFoundError(str(exc)) from exc
    raise DeletePreflightError("Неподдерживаемый тип удаления.")


def _prune_expired(now: float) -> None:
    expired = [operation_id for operation_id, grant in _GRANTS.items() if grant.expires_at <= now]
    for operation_id in expired:
        _GRANTS.pop(operation_id, None)


def issue_delete_preflight(settings: Settings, entity_type: str, entity_id: int) -> dict[str, object]:
    snapshot = _snapshot(settings, entity_type, entity_id)
    operation_id = uuid4().hex
    now = time.monotonic()
    grant = DeletePreflightGrant(
        operation_id=operation_id,
        entity_type=snapshot.entity_type,
        entity_id=snapshot.entity_id,
        fingerprint=snapshot.fingerprint,
        allowed=snapshot.allowed,
        expires_at=now + DELETE_PREFLIGHT_TTL_SECONDS,
    )
    with _GRANTS_LOCK:
        _prune_expired(now)
        _GRANTS[operation_id] = grant
    return {
        "entity_type": snapshot.entity_type,
        "entity_id": snapshot.entity_id,
        "allowed": snapshot.allowed,
        "blocked": not snapshot.allowed,
        "counts": dict(snapshot.counts),
        "blocking_reason": snapshot.blocking_reason,
        "message": snapshot.message,
        "operation_id": operation_id,
        "plan_fingerprint": snapshot.fingerprint,
        "expires_in_seconds": DELETE_PREFLIGHT_TTL_SECONDS,
    }


def _get_grant(operation_id: str) -> DeletePreflightGrant:
    now = time.monotonic()
    with _GRANTS_LOCK:
        _prune_expired(now)
        grant = _GRANTS.get(str(operation_id or ""))
    if grant is None:
        raise DeletePreflightValidationError("Проверка удаления устарела. Откройте подтверждение повторно.")
    return grant


def _recorded_plan_matches(settings: Settings, grant: DeletePreflightGrant) -> bool:
    try:
        plan = recorded_delete_plan(settings, grant.operation_id)
    except DeletionLifecycleError:
        return False
    if plan is None or not plan.entity_ids or plan.entity_ids[0] != grant.entity_id:
        return False
    expected_type = {
        "person": "person",
        "reward": "reward",
        "mark": "mark",
        "rank": "guide_rank",
    }.get(grant.entity_type, grant.entity_type.replace("guide_level_", "guide_lev_"))
    return plan.entity_type == expected_type


def authorize_delete_execution(
    settings: Settings,
    entity_type: str,
    entity_id: int,
    operation_id: str,
) -> None:
    grant = _get_grant(operation_id)
    normalized_type = str(entity_type or "").strip().lower()
    technical_id = int(entity_id)
    if grant.entity_type != normalized_type or grant.entity_id != technical_id:
        raise DeletePreflightValidationError("Идентификатор проверки не соответствует удаляемой записи.")
    if not grant.allowed:
        raise DeletePreflightValidationError("Удаление заблокировано актуальной проверкой.")
    try:
        current = _snapshot(settings, normalized_type, technical_id)
    except DeletePreflightNotFoundError:
        if _recorded_plan_matches(settings, grant):
            return
        raise DeletePreflightValidationError("Удаляемая запись изменилась после проверки.")
    if current.fingerprint != grant.fingerprint:
        raise DeletePreflightValidationError("Данные изменились после проверки удаления. Откройте подтверждение повторно.")


def reset_delete_preflight_registry() -> None:
    """Clear process-local grants for isolated tests."""
    with _GRANTS_LOCK:
        _GRANTS.clear()
