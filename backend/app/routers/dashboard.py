from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..repositories.common import table_counts
from .templates import templates


router = APIRouter()


@router.get("/")
def dashboard(request: Request):
    return RedirectResponse("/legacy?tab=rewards", status_code=307)


@router.head("/")
def dashboard_head():
    return RedirectResponse("/legacy?tab=rewards", status_code=307)


@router.get("/dashboard")
def dashboard_status(request: Request):
    settings = get_settings()
    counts = table_counts(settings.rewards_db_path) if settings.db_exists else {}
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"settings": settings, "counts": counts, "errors": settings.validation_errors()},
    )
