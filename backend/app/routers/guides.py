from fastapi import APIRouter, Request

from ..config import get_settings
from ..repositories.guides import guide_tree, list_rank_guide
from .templates import templates


router = APIRouter()


@router.get("/guides")
def guides_index(request: Request):
    settings = get_settings()
    ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
    tree = guide_tree(settings.rewards_db_path) if settings.db_exists else []
    return templates.TemplateResponse(
        request,
        "guides.html",
        {"settings": settings, "ranks": ranks, "tree": tree},
    )
