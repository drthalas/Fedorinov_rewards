from fastapi import APIRouter, Request

from ..config import get_settings
from ..repositories.search import search_all
from .templates import templates


router = APIRouter()


@router.get("/search")
def search_index(request: Request, q: str = ""):
    settings = get_settings()
    results = {"persons": [], "rewards": [], "marks": []}
    if q.strip() and settings.db_exists:
        results = search_all(settings.rewards_db_path, q)
    return templates.TemplateResponse(
        request,
        "search.html",
        {"settings": settings, "q": q, "results": results},
    )
