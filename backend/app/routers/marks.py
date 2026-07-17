from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from urllib.parse import parse_qs

from ..config import get_settings
from ..repositories.guides import guide_cascade_data, guide_cascade_options
from ..repositories.marks import count_marks, get_mark, list_marks, mark_photo_items
from ..repositories.marks_write import (
    MarkValidationError,
    create_mark,
    delete_mark_with_result,
    mark_data_from_mapping,
    mark_delete_confirmation_message,
    mark_delete_preview,
    update_mark,
)
from ..services.display import pagination
from ..services.navigation import delete_return_to, safe_return_to, with_query_value, with_status
from ..services.notifications import status_message
from ..services.photos import photo_items
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()


async def _read_form(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _write_error(exc: WriteBlockedError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


def _safe_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _selected_guides(row: dict[str, object] | None) -> dict[str, int | None]:
    if not row:
        return {"country_id": None, "category_id": None, "subcategory_id": None}
    return {
        "country_id": _safe_int(row.get("id_gos")),
        "category_id": _safe_int(row.get("id_catigory")),
        "subcategory_id": _safe_int(row.get("id_sub_catigory")),
    }


def _guide_options(settings, selected: dict[str, object] | None = None):
    if not settings.db_exists:
        return {"gos": [], "categories": [], "subcategories": [], "names": []}
    return guide_cascade_options(settings.rewards_db_path, **_selected_guides(selected))


def _guide_cascade(settings) -> dict[str, list[dict[str, object]]]:
    return guide_cascade_data(settings.rewards_db_path) if settings.db_exists else {}


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
            "status_message": status_message(status),
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
            "mark": {"instock": False, "date_purchase": date.today().isoformat()},
            "guides": _guide_options(settings),
            "guide_cascade": _guide_cascade(settings),
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
                "guides": _guide_options(settings, form_values),
                "guide_cascade": _guide_cascade(settings),
                "photo_controls": [],
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    target = with_status(return_to, "mark_created") if return_to else f"/marks/{mark_id}?status=mark_created"
    return RedirectResponse(target, status_code=303)


@router.get("/marks/{mark_id}")
def mark_detail(request: Request, mark_id: int, status: str = "", return_to: str = ""):
    settings = get_settings()
    mark = get_mark(settings.rewards_db_path, mark_id)
    if mark is None:
        raise HTTPException(status_code=404, detail="Знак не найден.")
    delete_preview = mark_delete_preview(settings, mark_id)
    return templates.TemplateResponse(
        request,
        "mark_detail.html",
        {
            "settings": settings,
            "mark": mark,
            "photos": mark_photo_items(mark),
            "status_message": status_message(status),
            "return_to": safe_return_to(return_to),
            "delete_operation_id": uuid4().hex,
            "delete_confirmation": mark_delete_confirmation_message(delete_preview),
            "delete_blocked": delete_preview.media.block_reason is not None,
        },
    )


@router.get("/marks/{mark_id}/edit")
def mark_edit(request: Request, mark_id: int, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    mark = get_mark(settings.rewards_db_path, mark_id)
    if mark is None:
        raise HTTPException(status_code=404, detail="Знак не найден.")
    return templates.TemplateResponse(
        request,
        "mark_form.html",
        {
            "settings": settings,
            "mode": "edit",
            "mark": mark,
            "guides": _guide_options(settings, mark),
            "guide_cascade": _guide_cascade(settings),
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
                "guides": _guide_options(settings, {**mark, **form_values}),
                "guide_cascade": _guide_cascade(settings),
                "photo_controls": photo_items("mark", mark),
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    target = with_status(return_to, "mark_updated") if return_to else f"/marks/{mark_id}?status=mark_updated"
    return RedirectResponse(target, status_code=303)


@router.post("/marks/{mark_id}/delete")
async def mark_delete(request: Request, mark_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        result = delete_mark_with_result(
            settings,
            mark_id,
            confirm=form_values.get("confirm") == "true",
            operation_id=str(form_values.get("delete_operation_id") or ""),
        )
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except MarkValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    success_return = delete_return_to(return_to, "mark_id")
    target = with_status(success_return, "mark_deleted") if success_return else "/marks?status=mark_deleted"
    if result.operation.warning_required:
        target = with_query_value(target, "media_cleanup", "failed")
    return RedirectResponse(target, status_code=303)
