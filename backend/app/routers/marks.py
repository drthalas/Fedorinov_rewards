from fastapi import APIRouter, HTTPException, Request

from ..config import get_settings
from ..repositories.marks import count_marks, get_mark, list_marks, mark_photo_items
from ..services.display import pagination
from .templates import templates


router = APIRouter()


@router.get("/marks")
def marks_index(request: Request, page: int = 1, page_size: int = 25):
    settings = get_settings()
    total = count_marks(settings.rewards_db_path) if settings.db_exists else 0
    pager = pagination(total, page, page_size)
    marks = (
        list_marks(settings.rewards_db_path, int(pager["page_size"]), int(pager["offset"]))
        if settings.db_exists
        else []
    )
    return templates.TemplateResponse(
        request,
        "marks.html",
        {"settings": settings, "marks": marks, "pagination": pager},
    )


@router.get("/marks/{mark_id}")
def mark_detail(request: Request, mark_id: int):
    settings = get_settings()
    mark = get_mark(settings.rewards_db_path, mark_id)
    if mark is None:
        raise HTTPException(status_code=404, detail="Mark not found")
    return templates.TemplateResponse(
        request,
        "mark_detail.html",
        {"settings": settings, "mark": mark, "photos": mark_photo_items(mark)},
    )
