from fastapi import APIRouter

from ..config import get_settings
from ..repositories.common import db_readable, table_counts
from ..services.runtime_identity import current_runtime_identity
from ..version import APP_VERSION


router = APIRouter()


@router.get("/runtime/identity")
def runtime_identity() -> dict[str, object]:
    settings = get_settings()
    return current_runtime_identity(
        version=APP_VERSION,
        install_root=settings.app_install_dir,
        host=settings.app_host,
        port=settings.app_port,
    )


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    readable = settings.db_exists and db_readable(settings.rewards_db_path)
    counts = table_counts(settings.rewards_db_path) if readable else {}

    return {
        "status": "ok" if settings.data_dir_exists and settings.db_exists and readable and not settings.validation_errors() else "warning",
        "read_only": settings.read_only,
        "write_mode": settings.write_mode,
        "data_dir": str(settings.rewards_data_dir),
        "db_exists": settings.db_exists,
        "db_readable": readable,
        "source_exists": settings.source_dir.exists() and settings.source_dir.is_dir(),
        "source_mark_exists": settings.source_mark_dir.exists() and settings.source_mark_dir.is_dir(),
        "nofoto_exists": settings.nofoto_path.exists() and settings.nofoto_path.is_file(),
        "counts": counts,
        "errors": settings.validation_errors(),
    }
