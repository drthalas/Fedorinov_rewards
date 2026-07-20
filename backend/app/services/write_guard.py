from ..config import Settings


class WriteBlockedError(RuntimeError):
    pass


def ensure_write_allowed(settings: Settings) -> None:
    if settings.read_only or not settings.write_mode:
        raise WriteBlockedError("Редактирование выключено.")


def ensure_dangerous_action_allowed(settings: Settings) -> None:
    if settings.read_only or not settings.write_mode:
        raise WriteBlockedError("Редактирование выключено.")
