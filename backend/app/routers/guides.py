from dataclasses import replace
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.datastructures import UploadFile

from ..config import get_settings
from ..repositories.guides import (
    get_guide_level_item,
    get_rank_guide_item,
    guide_level_item_lineage,
    guide_tree,
    list_guide_level,
    list_rank_guide,
)
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
from ..services.media_lifecycle import (
    MediaCleanupResult,
    cleanup_unreferenced_image,
    discard_uncommitted_image,
)
from ..services.guide_tree_state import (
    apply_guide_tree_state,
    guide_node_key,
    guide_tree_return_url,
)
from ..services.navigation import safe_return_to, with_status
from ..services.notifications import status_notification
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()

GUIDE_IMAGE_ROOTS = frozenset({"GuideImages"})

LEVEL_LABELS = {
    0: "Государство",
    1: "Категория",
    2: "Подкатегория",
    3: "Наименование",
    4: "Ссылка / дополнительный уровень",
}

CREATE_TITLES = {
    0: "Добавить государство",
    1: "Добавить категорию",
    2: "Добавить подкатегорию",
    3: "Добавить награду или знак",
    4: "Добавить ссылку",
}

GUIDE_BRANCH_TYPE_LABELS = {
    "ордена": "Орден",
    "орден": "Орден",
    "медали": "Медаль",
    "медаль": "Медаль",
    "знаки": "Знак",
    "знак": "Знак",
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


async def _read_rank_form(request: Request) -> tuple[dict[str, object], UploadFile | None]:
    return await _read_guide_level_form(request)


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


def _discard_guide_image_candidate(settings, image_path: object) -> MediaCleanupResult:
    return discard_uncommitted_image(settings, image_path, allowed_roots=GUIDE_IMAGE_ROOTS)


def _cleanup_replaced_guide_image(settings, image_path: object) -> MediaCleanupResult:
    return cleanup_unreferenced_image(settings, image_path, allowed_roots=GUIDE_IMAGE_ROOTS)


def _media_status(default_status: str, cleanup: MediaCleanupResult | None) -> str:
    return "media_cleanup_failed" if cleanup is not None and cleanup.warning_required else default_status


def _write_error(exc: WriteBlockedError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


def _delete_validation_error(exc: GuideValidationError) -> HTTPException:
    status_code = 400 if str(exc) == "Действие требует подтверждения." else 404
    return HTTPException(status_code=status_code, detail=str(exc))


def _guide_item_display_title(settings, level: int, item: dict[str, object]) -> str:
    name = str(item.get("name") or "").strip()
    if not name:
        return "Изменить элемент справочника"
    if level != 3:
        return name
    lineage = guide_level_item_lineage(settings.rewards_db_path, level, int(item.get("id") or 0))
    for ancestor in reversed(lineage[:-1]):
        branch_name = str(ancestor.get("name") or "").strip().casefold().replace("ё", "е")
        type_label = GUIDE_BRANCH_TYPE_LABELS.get(branch_name)
        if type_label:
            type_prefix = type_label.casefold().replace("ё", "е") + " "
            display_name = name[len(type_prefix):] if name.casefold().replace("ё", "е").startswith(type_prefix) else name
            return f"{type_label}: {display_name}"
    return name


def _supports_award_media(level: int) -> bool:
    return level == 3


def _context(
    settings,
    request: Request,
    return_to: str = "",
    status: str = "",
    error: str | None = None,
    section: str = "",
    open_nodes: str = "",
    focus: str = "",
):
    ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
    tree = guide_tree(settings.rewards_db_path) if settings.db_exists else []
    safe_open, safe_focus = apply_guide_tree_state(tree, open_nodes, focus)
    safe_return = safe_return_to(return_to)
    safe_section = section if section in {"ranks", "tree"} else ""
    guides_self = "/guides"
    query: dict[str, str] = {}
    if safe_section:
        query["section"] = safe_section
    if safe_return:
        query["return_to"] = safe_return
    if safe_open:
        query["open"] = ",".join(safe_open)
    if safe_focus:
        query["focus"] = safe_focus
    if query:
        guides_self += "?" + urlencode(query)
    notification = status_notification(status)
    status_message = notification.message if notification is not None else None
    status_kind = notification.kind if notification is not None else "success"
    return {
        "settings": settings,
        "ranks": ranks,
        "tree": tree,
        "return_to": safe_return,
        "section": safe_section,
        "guides_self": guides_self,
        "guide_open": safe_open,
        "guide_focus": safe_focus,
        "status_message": status_message,
        "status_kind": status_kind,
        "status_timeout_ms": notification.timeout_ms if notification is not None else 4000,
        "error": error,
        "notification_error_message": error,
    }


def _parent_options(settings, level: int) -> list[dict[str, object]]:
    if level <= 0 or not settings.db_exists:
        return []
    return list_guide_level(settings.rewards_db_path, level - 1)


@router.get("/guides")
def guides_index(
    request: Request,
    return_to: str = "",
    status: str = "",
    section: str = "",
    open: str = "",
    focus: str = "",
):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "guides.html",
        _context(settings, request, return_to, status, section=section, open_nodes=open, focus=focus),
    )


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
    form_values, upload = await _read_rank_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    image_path: str | None = None
    try:
        data = rank_data_from_mapping(form_values)
        image_path = await _save_uploaded_guide_image(settings, upload)
        if image_path:
            data = replace(data, image_path=image_path)
        create_rank(settings, data)
    except WriteBlockedError as exc:
        _discard_guide_image_candidate(settings, image_path)
        raise _write_error(exc) from exc
    except (GuideValidationError, GuideImageValidationError) as exc:
        _discard_guide_image_candidate(settings, image_path)
        return templates.TemplateResponse(
            request,
            "rank_form.html",
            {"settings": settings, "mode": "create", "rank": form_values, "return_to": return_to, "error": str(exc)},
            status_code=400,
        )
    except Exception:
        _discard_guide_image_candidate(settings, image_path)
        raise
    finally:
        if upload is not None:
            await upload.close()
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
    current_rank = get_rank_guide_item(settings.rewards_db_path, rank_id) if settings.db_exists else None
    if current_rank is None:
        raise HTTPException(status_code=404, detail="Звание/специальность не найдены.")
    form_values, upload = await _read_rank_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    old_image_path = current_rank.get("image_path")
    new_image_path: str | None = None
    resulting_image_path: object = old_image_path
    try:
        data = rank_data_from_mapping(form_values)
        new_image_path = await _save_uploaded_guide_image(settings, upload)
        if new_image_path:
            image_path = new_image_path
        elif form_values.get("clear_image") == "true":
            image_path = None
        else:
            image_path = old_image_path
        resulting_image_path = image_path
        update_rank(settings, rank_id, replace(data, image_path=image_path))
    except WriteBlockedError as exc:
        _discard_guide_image_candidate(settings, new_image_path)
        raise _write_error(exc) from exc
    except (GuideValidationError, GuideImageValidationError) as exc:
        _discard_guide_image_candidate(settings, new_image_path)
        return templates.TemplateResponse(
            request,
            "rank_form.html",
            {
                "settings": settings,
                "mode": "edit",
                "rank": {**current_rank, "id": rank_id, **form_values, "image_path": old_image_path},
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    except Exception:
        _discard_guide_image_candidate(settings, new_image_path)
        raise
    finally:
        if upload is not None:
            await upload.close()
    cleanup = None
    if old_image_path and old_image_path != resulting_image_path:
        cleanup = _cleanup_replaced_guide_image(settings, old_image_path)
    status_code = _media_status("rank_updated", cleanup)
    target = with_status(return_to, status_code) if return_to else f"/guides?status={status_code}"
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
            "form_title": CREATE_TITLES[level],
            "supports_award_media": _supports_award_media(level),
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
    supports_award_media = _supports_award_media(level)
    try:
        if not supports_award_media:
            form_values["rating_rank"] = ""
        data = guide_level_data_from_mapping(level, form_values)
        image_path = await _save_uploaded_guide_image(settings, upload) if supports_award_media else None
        if image_path:
            data = replace(data, image_path=image_path)
        created_item_id = create_guide_level_item(settings, data)
    except WriteBlockedError as exc:
        _discard_guide_image_candidate(settings, image_path)
        raise _write_error(exc) from exc
    except (GuideValidationError, GuideImageValidationError) as exc:
        _discard_guide_image_candidate(settings, image_path)
        return templates.TemplateResponse(
            request,
            "guide_level_form.html",
            {
                "settings": settings,
                "mode": "create",
                "item": {"level": level, **form_values},
                "level": level,
                "level_label": LEVEL_LABELS.get(level, "Элемент справочника"),
                "form_title": CREATE_TITLES.get(level, "Добавить элемент справочника"),
                "supports_award_media": supports_award_media,
                "parent_options": _parent_options(settings, level),
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    except Exception:
        _discard_guide_image_candidate(settings, image_path)
        raise
    finally:
        if upload is not None:
            await upload.close()
    if return_to:
        parent_key = guide_node_key(level - 1, data.parent_id) if level > 0 else ""
        target = guide_tree_return_url(
            return_to,
            focus_key=guide_node_key(level, created_item_id),
            add_open_keys=(parent_key,) if parent_key else (),
        )
        target = with_status(target, "guide_created")
    else:
        target = "/guides?status=guide_created"
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
            "display_title": _guide_item_display_title(settings, level, item),
            "supports_award_media": _supports_award_media(level),
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
    supports_award_media = _supports_award_media(level)
    try:
        if not supports_award_media:
            form_values["rating_rank"] = ""
        data = guide_level_data_from_mapping(level, form_values)
        new_image_path = await _save_uploaded_guide_image(settings, upload) if supports_award_media else None
        if supports_award_media:
            data = replace(data, image_path=new_image_path or old_image_path)
        else:
            data = replace(
                data,
                rating_rank=current_item.get("rating_rank"),
                image_path=old_image_path,
            )
        update_guide_level_item(settings, level, item_id, data)
    except WriteBlockedError as exc:
        _discard_guide_image_candidate(settings, new_image_path)
        raise _write_error(exc) from exc
    except (GuideValidationError, GuideImageValidationError) as exc:
        _discard_guide_image_candidate(settings, new_image_path)
        return templates.TemplateResponse(
            request,
            "guide_level_form.html",
            {
                "settings": settings,
                "mode": "edit",
                "item": {**current_item, "id": item_id, "level": level, **form_values},
                "level": level,
                "level_label": LEVEL_LABELS.get(level, "Элемент справочника"),
                "display_title": _guide_item_display_title(settings, level, current_item),
                "supports_award_media": supports_award_media,
                "parent_options": _parent_options(settings, level),
                "return_to": return_to,
                "error": str(exc),
            },
            status_code=400,
        )
    except Exception:
        _discard_guide_image_candidate(settings, new_image_path)
        raise
    finally:
        if upload is not None:
            await upload.close()
    cleanup = None
    if new_image_path and old_image_path and old_image_path != new_image_path:
        cleanup = _cleanup_replaced_guide_image(settings, old_image_path)
    status_code = _media_status("guide_updated", cleanup)
    if return_to:
        target = guide_tree_return_url(return_to, focus_key=guide_node_key(level, item_id))
        target = with_status(target, status_code)
    else:
        target = f"/guides?status={status_code}"
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
        cleanup = _cleanup_replaced_guide_image(settings, image_path)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except GuideValidationError as exc:
        raise _delete_validation_error(exc) from exc
    status_code = _media_status("guide_image_deleted", cleanup)
    target = with_status(return_to, status_code) if return_to else f"/guides?status={status_code}"
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
