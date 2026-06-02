from ..config import Settings
from .backup_state import check_recent_backup_exists


class WriteBlockedError(RuntimeError):
    pass


def ensure_write_allowed(settings: Settings) -> None:
    if not settings.write_mode:
        raise WriteBlockedError("WRITE_MODE=true is required for changes")
    if settings.require_backup_before_write and not check_recent_backup_exists(settings.rewards_data_dir):
        raise WriteBlockedError("Create a fresh backup before making changes")
