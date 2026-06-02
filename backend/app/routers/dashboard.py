from fastapi import APIRouter, Request

from ..config import get_settings
from ..repositories.common import table_counts
from .templates import templates


router = APIRouter()


@router.get("/")
def dashboard(request: Request):
    settings = get_settings()
    counts = table_counts(settings.rewards_db_path) if settings.db_exists else {}
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"settings": settings, "counts": counts, "errors": settings.validation_errors()},
    )
