from fastapi import APIRouter, Request

from ..config import get_settings
from ..repositories.search import search_all
from .templates import templates


router = APIRouter()


@router.get("/search")
def search_index(request: Request, q: str = ""):
    settings = get_settings()
    results = {"persons": [], "rewards": [], "marks": [], "counts": {"persons": 0, "rewards": 0, "marks": 0}, "limit": 25}
    if q.strip() and settings.db_exists:
        results = search_all(settings.rewards_db_path, q, limit=25)
    return templates.TemplateResponse(
        request,
        "search.html",
        {"settings": settings, "q": q, "results": results},
    )
