from fastapi import APIRouter

from ..config import get_settings
from ..repositories.common import db_readable, table_counts


router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    readable = settings.db_exists and db_readable(settings.rewards_db_path)
    counts = table_counts(settings.rewards_db_path) if readable else {}

    return {
        "status": "ok" if settings.data_dir_exists and settings.db_exists and readable and settings.read_only else "warning",
        "read_only": settings.read_only,
        "write_mode": settings.write_mode,
        "require_backup_before_write": settings.require_backup_before_write,
        "data_dir": str(settings.rewards_data_dir),
        "db_exists": settings.db_exists,
        "db_readable": readable,
        "source_exists": settings.source_dir.exists() and settings.source_dir.is_dir(),
        "source_mark_exists": settings.source_mark_dir.exists() and settings.source_mark_dir.is_dir(),
        "nofoto_exists": settings.nofoto_path.exists() and settings.nofoto_path.is_file(),
        "counts": counts,
        "errors": settings.validation_errors(),
    }
