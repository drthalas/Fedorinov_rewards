from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from urllib.parse import parse_qs

from ..config import get_settings
from ..repositories.guides import list_guide_level
from ..repositories.marks import count_marks, get_mark, list_marks, mark_photo_items
from ..repositories.marks_write import (
    MarkValidationError,
    create_mark,
    delete_mark,
    mark_data_from_mapping,
    update_mark,
)
from ..services.display import pagination
from ..services.navigation import safe_return_to, with_status
from ..services.photos import photo_items
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()


STATUS_MESSAGES = {
    "mark_created": "Знак добавлен.",
    "created": "Знак добавлен.",
    "updated": "Изменения сохранены.",
    "mark_deleted": "Знак удален.",
}


async def _read_form(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _write_error(exc: WriteBlockedError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


def _guide_options(settings):
    if not settings.db_exists:
        return {"gos": [], "categories": [], "subcategories": [], "names": []}
    return {
        "gos": list_guide_level(settings.rewards_db_path, 0),
        "categories": list_guide_level(settings.rewards_db_path, 1),
        "subcategories": list_guide_level(settings.rewards_db_path, 2),
        "names": list_guide_level(settings.rewards_db_path, 3),
    }


@router.get("/marks")
def marks_index(request: Request, page: int = 1, page_size: int = 25, status: str = ""):
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
        {
            "settings": settings,
            "marks": marks,
            "pagination": pager,
            "status_message": STATUS_MESSAGES.get(status),
        },
    )


@router.get("/marks/new")
def mark_new(request: Request, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    return templates.TemplateResponse(
        request,
        "mark_form.html",
        {
            "settings": settings,
            "mode": "create",
            "mark": {"instock": False},
            "guides": _guide_options(settings),
            "photo_controls": [],
            "return_to": safe_return_to(return_to),
            "error": None,
        },
    )


@router.post("/marks/new")
async def mark_create(request: Request):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        data = mark_data_from_mapping(form_values)
        mark_id = create_mark(settings, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except MarkValidationError as exc:
        return templates.TemplateResponse(
            request,
            "mark_form.html",
            {
                "settings": settings,
                "mode": "create",
                "mark": form_values,
                "guides": _guide_options(settings),
                "photo_controls": [],
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    target = with_status(return_to, "mark_created") if return_to else f"/marks/{mark_id}?status=created"
    return RedirectResponse(target, status_code=303)


@router.get("/marks/{mark_id}")
def mark_detail(request: Request, mark_id: int, status: str = ""):
    settings = get_settings()
    mark = get_mark(settings.rewards_db_path, mark_id)
    if mark is None:
        raise HTTPException(status_code=404, detail="Mark not found")
    return templates.TemplateResponse(
        request,
        "mark_detail.html",
        {
            "settings": settings,
            "mark": mark,
            "photos": mark_photo_items(mark),
            "status_message": STATUS_MESSAGES.get(status),
        },
    )


@router.get("/marks/{mark_id}/edit")
def mark_edit(request: Request, mark_id: int, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    mark = get_mark(settings.rewards_db_path, mark_id)
    if mark is None:
        raise HTTPException(status_code=404, detail="Mark not found")
    return templates.TemplateResponse(
        request,
        "mark_form.html",
        {
            "settings": settings,
            "mode": "edit",
            "mark": mark,
            "guides": _guide_options(settings),
            "photo_controls": photo_items("mark", mark),
            "return_to": safe_return_to(return_to),
            "error": None,
        },
    )


@router.post("/marks/{mark_id}/edit")
async def mark_update(request: Request, mark_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        data = mark_data_from_mapping(form_values)
        update_mark(settings, mark_id, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except MarkValidationError as exc:
        mark = get_mark(settings.rewards_db_path, mark_id) or {"id": mark_id}
        return templates.TemplateResponse(
            request,
            "mark_form.html",
            {
                "settings": settings,
                "mode": "edit",
                "mark": {**mark, **form_values},
                "guides": _guide_options(settings),
                "photo_controls": photo_items("mark", mark),
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    target = with_status(return_to, "updated") if return_to else f"/marks/{mark_id}?status=updated"
    return RedirectResponse(target, status_code=303)


@router.post("/marks/{mark_id}/delete")
async def mark_delete(request: Request, mark_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        delete_mark(settings, mark_id, confirm=form_values.get("confirm") == "true")
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except MarkValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target = with_status(return_to, "mark_deleted") if return_to else "/marks?status=mark_deleted"
    return RedirectResponse(target, status_code=303)
