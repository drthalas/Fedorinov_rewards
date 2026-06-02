from datetime import datetime, timedelta
from pathlib import Path


def backup_dir_for_data_root(data_dir: Path) -> Path:
    return data_dir.expanduser().resolve().parent / "backups"


def check_recent_backup_exists(data_dir: Path, max_age_hours: int = 24) -> bool:
    backup_dir = backup_dir_for_data_root(data_dir)
    if not backup_dir.exists() or not backup_dir.is_dir():
        return False

    cutoff = datetime.now().timestamp() - timedelta(hours=max_age_hours).total_seconds()
    for backup in backup_dir.glob("Rewards_backup_*.zip"):
        if backup.is_file() and backup.stat().st_mtime >= cutoff:
            return True
    return False
