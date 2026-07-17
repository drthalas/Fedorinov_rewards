from dataclasses import dataclass
from typing import Mapping


SUCCESS_TIMEOUT_MS = 4000
ATTENTION_TIMEOUT_MS = 8000
MAX_VISIBLE_NOTIFICATIONS = 3


@dataclass(frozen=True)
class NotificationSpec:
    message: str
    kind: str = "success"

    @property
    def timeout_ms(self) -> int:
        return SUCCESS_TIMEOUT_MS if self.kind == "success" else ATTENTION_TIMEOUT_MS


STATUS_NOTIFICATIONS: Mapping[str, NotificationSpec] = {
    "person_created": NotificationSpec("Кавалер создан."),
    "person_updated": NotificationSpec("Кавалер сохранён."),
    "person_deleted": NotificationSpec("Кавалер удалён."),
    "delete_blocked": NotificationSpec(
        "Нельзя удалить кавалера: сначала удалите или перенесите его награды.",
        "error",
    ),
    "reward_created": NotificationSpec("Награда добавлена."),
    "reward_updated": NotificationSpec("Награда сохранена."),
    "reward_deleted": NotificationSpec("Награда удалена."),
    "mark_created": NotificationSpec("Знак добавлен."),
    "mark_updated": NotificationSpec("Знак сохранён."),
    "mark_deleted": NotificationSpec("Знак удалён."),
    "photo_updated": NotificationSpec("Фотография обновлена."),
    "photo_cleared": NotificationSpec("Фотография удалена."),
    "folder_opened": NotificationSpec("Каталог кавалера открыт."),
    "folder_missing": NotificationSpec("Каталог кавалера не найден.", "error"),
    "archive_empty": NotificationSpec("В каталоге кавалера нет файлов для архивации.", "warning"),
    "archive_cancelled": NotificationSpec("Сохранение отменено.", "warning"),
    "save_dialog_unavailable": NotificationSpec("Не удалось открыть окно сохранения.", "error"),
    "rank_created": NotificationSpec("Звание/специальность добавлены."),
    "rank_updated": NotificationSpec("Звание/специальность сохранены."),
    "rank_deleted": NotificationSpec("Звание/специальность удалены."),
    "guide_created": NotificationSpec("Элемент справочника добавлен."),
    "guide_updated": NotificationSpec("Элемент справочника сохранён."),
    "guide_deleted": NotificationSpec("Элемент справочника удалён."),
    "guide_image_deleted": NotificationSpec("Изображение элемента справочника удалено."),
    "rank_delete_used": NotificationSpec(
        "Нельзя удалить: это звание используется в карточках кавалеров.",
        "error",
    ),
    "guide_delete_children": NotificationSpec(
        "Нельзя удалить: у этого раздела есть дочерние записи.",
        "error",
    ),
    "guide_delete_used": NotificationSpec(
        "Нельзя удалить: это значение используется в наградах или знаках.",
        "error",
    ),
    "media_cleanup_failed": NotificationSpec(
        "Изменения сохранены, но старый файл не удалось удалить. Проверьте журнал приложения.",
        "warning",
    ),
    # Backward-compatible markers from older bookmarks and redirects.
    "created": NotificationSpec("Запись добавлена."),
    "updated": NotificationSpec("Изменения сохранены."),
    "deleted": NotificationSpec("Запись удалена."),
}


def status_notification(status: object) -> NotificationSpec | None:
    return STATUS_NOTIFICATIONS.get(str(status or "").strip())


def status_message(status: object) -> str | None:
    notification = status_notification(status)
    return notification.message if notification is not None else None


def _message_kind(message: str) -> str:
    lowered = message.casefold()
    if "отмен" in lowered:
        return "warning"
    if any(marker in lowered for marker in ("не удалось", "ошиб", "недоступ", "нельзя")):
        return "error"
    return "success"


def _item(spec: NotificationSpec, query_keys: tuple[str, ...] = ()) -> dict[str, object]:
    return {
        "message": spec.message,
        "kind": spec.kind,
        "timeout_ms": spec.timeout_ms,
        "query_keys": query_keys,
    }


def transient_notifications(
    request,
    status_message_value: object = "",
    status_kind: object = "",
    created_message: object = "",
    message: object = "",
    error_message: object = "",
    notification_error_message: object = "",
) -> list[dict[str, object]]:
    query = getattr(request, "query_params", {})
    notifications: list[dict[str, object]] = []
    seen_messages: set[str] = set()

    def add(spec: NotificationSpec, query_keys: tuple[str, ...] = ()) -> None:
        if not spec.message or spec.message in seen_messages:
            return
        seen_messages.add(spec.message)
        notifications.append(_item(spec, query_keys))

    cleanup_failed = str(query.get("media_cleanup", "")) == "failed"
    if cleanup_failed:
        add(STATUS_NOTIFICATIONS["media_cleanup_failed"], ("media_cleanup", "status"))
    else:
        status = str(query.get("status", ""))
        spec = status_notification(status)
        if spec is None and status_message_value:
            kind = str(status_kind or "success")
            spec = NotificationSpec(str(status_message_value), kind if kind in {"success", "warning", "error"} else "success")
        if spec is not None:
            add(spec, ("status",))

    if str(query.get("created", "")) and created_message:
        add(NotificationSpec(str(created_message)), ("created",))

    clean_message = str(message or "").strip()
    if clean_message and clean_message != "pdf_not_implemented":
        add(NotificationSpec(clean_message, _message_kind(clean_message)), ("message",))

    clean_error = str(error_message or "").strip()
    if clean_error:
        add(NotificationSpec(clean_error, "error"), ("error",))

    operation_error = str(notification_error_message or "").strip()
    if operation_error:
        add(NotificationSpec(operation_error, "error"))

    return notifications[:MAX_VISIBLE_NOTIFICATIONS]
