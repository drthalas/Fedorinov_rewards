from dataclasses import replace
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.datastructures import UploadFile

from ..config import get_settings
from ..repositories.guides import get_guide_level_item, get_rank_guide_item, guide_tree, list_guide_level, list_rank_guide
from ..repositories.guides_write import (
    GuideDeleteBlockedError,
    GuideValidationError,
    clear_guide_level_image,
    create_guide_level_item,
    create_rank,
    delete_guide_level_item,
    delete_rank,
    guide_level_data_from_mapping,
    rank_data_from_mapping,
    update_guide_level_item,
    update_rank,
)
from ..services.guide_images import (
    MAX_GUIDE_IMAGE_BYTES,
    GuideImageValidationError,
    delete_guide_image_file,
    save_guide_image,
)
from ..services.navigation import safe_return_to, with_status
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()

STATUS_MESSAGES = {
    "rank_created": "Звание/специальность добавлены.",
    "rank_updated": "Звание/специальность сохранены.",
    "rank_deleted": "Звание/специальность удалены.",
    "guide_created": "Элемент справочника добавлен.",
    "guide_updated": "Элемент справочника сохранён.",
    "guide_deleted": "Элемент справочника удалён.",
    "guide_image_deleted": "Изображение элемента справочника удалено.",
    "delete_blocked": "Удаление заблокировано: значение используется или имеет дочерние записи.",
    "rank_delete_used": "Нельзя удалить: это звание используется в карточках награждённых.",
    "guide_delete_children": "Нельзя удалить: у этого раздела есть дочерние записи.",
    "guide_delete_used": "Нельзя удалить: это значение используется в наградах или знаках.",
}

LEVEL_LABELS = {
    0: "Государство",
    1: "Категория",
    2: "Подкатегория",
    3: "Наименование",
    4: "Ссылка / дополнительный уровень",
}


async def _read_form(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


async def _read_guide_level_form(request: Request) -> tuple[dict[str, object], UploadFile | None]:
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Для формы требуется multipart/form-data.") from exc
    values = {
        key: value
        for key, value in form.multi_items()
        if not isinstance(value, UploadFile)
    }
    upload = form.get("image_file")
    return values, upload if isinstance(upload, UploadFile) else None


async def _save_uploaded_guide_image(settings, upload: UploadFile | None) -> str | None:
    if upload is None or not (upload.filename or "").strip():
        return None
    content = await upload.read(MAX_GUIDE_IMAGE_BYTES + 1)
    return save_guide_image(settings, upload.filename or "", content)


def _delete_guide_image_safely(settings, image_path: object) -> None:
    if image_path is None or image_path == "":
        return
    try:
        delete_guide_image_file(settings, image_path)
    except (GuideImageValidationError, OSError):
        return


def _write_error(exc: WriteBlockedError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


def _delete_validation_error(exc: GuideValidationError) -> HTTPException:
    status_code = 400 if str(exc) == "Действие требует подтверждения." else 404
    return HTTPException(status_code=status_code, detail=str(exc))


def _context(settings, request: Request, return_to: str = "", status: str = "", error: str | None = None, section: str = ""):
    ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
    tree = guide_tree(settings.rewards_db_path) if settings.db_exists else []
    safe_return = safe_return_to(return_to)
    safe_section = section if section in {"ranks", "tree"} else ""
    guides_self = "/guides"
    query: dict[str, str] = {}
    if safe_section:
        query["section"] = safe_section
    if safe_return:
        query["return_to"] = safe_return
    if query:
        guides_self += "?" + urlencode(query)
    return {
        "settings": settings,
        "ranks": ranks,
        "tree": tree,
        "return_to": safe_return,
        "section": safe_section,
        "guides_self": guides_self,
        "status_message": STATUS_MESSAGES.get(status),
        "error": error,
    }


def _parent_options(settings, level: int) -> list[dict[str, object]]:
    if level <= 0 or not settings.db_exists:
        return []
    return list_guide_level(settings.rewards_db_path, level - 1)


@router.get("/guides")
def guides_index(request: Request, return_to: str = "", status: str = "", section: str = ""):
    settings = get_settings()
    return templates.TemplateResponse(request, "guides.html", _context(settings, request, return_to, status, section=section))


@router.get("/guides/ranks/new")
def rank_new(request: Request, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    return templates.TemplateResponse(
        request,
        "rank_form.html",
        {"settings": settings, "mode": "create", "rank": {}, "return_to": safe_return_to(return_to), "error": None},
    )


@router.post("/guides/ranks/new")
async def rank_create(request: Request):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        create_rank(settings, rank_data_from_mapping(form_values))
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except GuideValidationError as exc:
        return templates.TemplateResponse(
            request,
            "rank_form.html",
            {"settings": settings, "mode": "create", "rank": form_values, "return_to": return_to, "error": str(exc)},
            status_code=400,
        )
    target = with_status(return_to, "rank_created") if return_to else "/guides?status=rank_created"
    return RedirectResponse(target, status_code=303)


@router.get("/guides/ranks/{rank_id}/edit")
def rank_edit(request: Request, rank_id: int, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    rank = get_rank_guide_item(settings.rewards_db_path, rank_id)
    if rank is None:
        raise HTTPException(status_code=404, detail="Звание/специальность не найдены.")
    return templates.TemplateResponse(
        request,
        "rank_form.html",
        {"settings": settings, "mode": "edit", "rank": rank, "return_to": safe_return_to(return_to), "error": None},
    )


@router.post("/guides/ranks/{rank_id}/edit")
async def rank_update(request: Request, rank_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        update_rank(settings, rank_id, rank_data_from_mapping(form_values))
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except GuideValidationError as exc:
        return templates.TemplateResponse(
            request,
            "rank_form.html",
            {"settings": settings, "mode": "edit", "rank": {"id": rank_id, **form_values}, "return_to": return_to, "error": str(exc)},
            status_code=400,
        )
    target = with_status(return_to, "rank_updated") if return_to else "/guides?status=rank_updated"
    return RedirectResponse(target, status_code=303)


@router.post("/guides/ranks/{rank_id}/delete")
async def rank_delete(request: Request, rank_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        delete_rank(settings, rank_id, confirm=form_values.get("confirm") == "true")
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except GuideDeleteBlockedError:
        target = with_status(return_to, "rank_delete_used") if return_to else "/guides?status=rank_delete_used"
        return RedirectResponse(target, status_code=303)
    except GuideValidationError as exc:
        raise _delete_validation_error(exc) from exc
    target = with_status(return_to, "rank_deleted") if return_to else "/guides?status=rank_deleted"
    return RedirectResponse(target, status_code=303)


@router.get("/guides/levels/{level}/new")
def guide_level_new(request: Request, level: int, parent_id: int | None = None, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    if level not in LEVEL_LABELS:
        raise HTTPException(status_code=404, detail="Раздел справочника не найден.")
    item = {"level": level, "parent_id": parent_id if parent_id is not None else ""}
    return templates.TemplateResponse(
        request,
        "guide_level_form.html",
        {
            "settings": settings,
            "mode": "create",
            "item": item,
            "level": level,
            "level_label": LEVEL_LABELS[level],
            "parent_options": _parent_options(settings, level),
            "return_to": safe_return_to(return_to),
            "error": None,
        },
    )


@router.post("/guides/levels/{level}/new")
async def guide_level_create(request: Request, level: int):
    settings = get_settings()
    form_values, upload = await _read_guide_level_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    image_path: str | None = None
    try:
        data = guide_level_data_from_mapping(level, form_values)
        image_path = await _save_uploaded_guide_image(settings, upload)
        if image_path:
            data = replace(data, image_path=image_path)
        create_guide_level_item(settings, data)
    except WriteBlockedError as exc:
        _delete_guide_image_safely(settings, image_path)
        raise _write_error(exc) from exc
    except (GuideValidationError, GuideImageValidationError) as exc:
        _delete_guide_image_safely(settings, image_path)
        return templates.TemplateResponse(
            request,
            "guide_level_form.html",
            {
                "settings": settings,
                "mode": "create",
                "item": {"level": level, **form_values},
                "level": level,
                "level_label": LEVEL_LABELS.get(level, "Элемент справочника"),
                "parent_options": _parent_options(settings, level),
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    finally:
        if upload is not None:
            await upload.close()
    target = with_status(return_to, "guide_created") if return_to else "/guides?status=guide_created"
    return RedirectResponse(target, status_code=303)


@router.get("/guides/levels/{level}/{item_id}/edit")
def guide_level_edit(request: Request, level: int, item_id: int, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    if level not in LEVEL_LABELS:
        raise HTTPException(status_code=404, detail="Раздел справочника не найден.")
    item = get_guide_level_item(settings.rewards_db_path, level, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Элемент справочника не найден.")
    return templates.TemplateResponse(
        request,
        "guide_level_form.html",
        {
            "settings": settings,
            "mode": "edit",
            "item": item,
            "level": level,
            "level_label": LEVEL_LABELS[level],
            "parent_options": _parent_options(settings, level),
            "return_to": safe_return_to(return_to),
            "error": None,
        },
    )


@router.post("/guides/levels/{level}/{item_id}/edit")
async def guide_level_update(request: Request, level: int, item_id: int):
    settings = get_settings()
    current_item = get_guide_level_item(settings.rewards_db_path, level, item_id) if settings.db_exists else None
    if current_item is None:
        raise HTTPException(status_code=404, detail="Элемент справочника не найден.")
    form_values, upload = await _read_guide_level_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    old_image_path = current_item.get("image_path")
    new_image_path: str | None = None
    try:
        data = guide_level_data_from_mapping(level, form_values)
        new_image_path = await _save_uploaded_guide_image(settings, upload)
        data = replace(data, image_path=new_image_path or old_image_path)
        update_guide_level_item(settings, level, item_id, data)
    except WriteBlockedError as exc:
        _delete_guide_image_safely(settings, new_image_path)
        raise _write_error(exc) from exc
    except (GuideValidationError, GuideImageValidationError) as exc:
        _delete_guide_image_safely(settings, new_image_path)
        return templates.TemplateResponse(
            request,
            "guide_level_form.html",
            {
                "settings": settings,
                "mode": "edit",
                "item": {**current_item, "id": item_id, "level": level, **form_values},
                "level": level,
                "level_label": LEVEL_LABELS.get(level, "Элемент справочника"),
                "parent_options": _parent_options(settings, level),
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    finally:
        if upload is not None:
            await upload.close()
    if new_image_path and old_image_path and old_image_path != new_image_path:
        _delete_guide_image_safely(settings, old_image_path)
    target = with_status(return_to, "guide_updated") if return_to else "/guides?status=guide_updated"
    return RedirectResponse(target, status_code=303)


@router.post("/guides/levels/{level}/{item_id}/image/delete")
async def guide_level_image_delete(request: Request, level: int, item_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    if form_values.get("confirm") != "true":
        raise HTTPException(status_code=400, detail="Действие требует подтверждения.")
    try:
        image_path = clear_guide_level_image(settings, level, item_id)
        _delete_guide_image_safely(settings, image_path)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except GuideValidationError as exc:
        raise _delete_validation_error(exc) from exc
    target = with_status(return_to, "guide_image_deleted") if return_to else "/guides?status=guide_image_deleted"
    return RedirectResponse(target, status_code=303)


@router.post("/guides/levels/{level}/{item_id}/delete")
async def guide_level_delete(request: Request, level: int, item_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    item = get_guide_level_item(settings.rewards_db_path, level, item_id) if settings.db_exists else None
    try:
        delete_guide_level_item(settings, level, item_id, confirm=form_values.get("confirm") == "true")
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except GuideDeleteBlockedError as exc:
        status_code = "guide_delete_children" if "дочер" in str(exc).lower() else "guide_delete_used"
        target = with_status(return_to, status_code) if return_to else f"/guides?status={status_code}"
        return RedirectResponse(target, status_code=303)
    except GuideValidationError as exc:
        raise _delete_validation_error(exc) from exc
    if item is not None:
        _delete_guide_image_safely(settings, item.get("image_path"))
    target = with_status(return_to, "guide_deleted") if return_to else "/guides?status=guide_deleted"
    return RedirectResponse(target, status_code=303)
