from ..config import Settings
from .backup_state import check_recent_backup_exists


class WriteBlockedError(RuntimeError):
    pass


def ensure_write_allowed(settings: Settings) -> None:
    if settings.read_only or not settings.write_mode:
        raise WriteBlockedError("Редактирование выключено.")
    if settings.require_backup_before_write and not check_recent_backup_exists(settings.rewards_data_dir):
        raise WriteBlockedError("Перед этим действием нужно создать резервную копию.")


def ensure_dangerous_action_allowed(settings: Settings) -> None:
    ensure_write_allowed(settings)
    if settings.require_backup_before_dangerous_actions and not check_recent_backup_exists(settings.rewards_data_dir):
        raise WriteBlockedError("Перед этим действием нужно создать резервную копию.")
