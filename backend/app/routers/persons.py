import logging
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from ..config import get_settings
from ..repositories.guides import list_rank_guide
from ..repositories.persons import count_persons, get_person, list_person_rewards, list_persons, person_photo_items
from ..repositories.persons_write import (
    PersonDeleteBlockedError,
    PersonValidationError,
    create_person,
    delete_person_with_result,
    person_data_from_mapping,
    update_person,
)
from ..repositories.reward_reference import list_reward_references
from ..repositories.rewards_write import RewardValidationError
from ..services.delete_preflight import DeletePreflightValidationError, authorize_delete_execution
from ..services.dates import BIRTH_YEAR_MAXIMUM, BIRTH_YEAR_MINIMUM
from ..services.display import pagination
from ..services.booklets import BookletError, generate_person_booklet_pdf, person_booklet_context, person_booklet_filename
from ..services.navigation import delete_preflight_retry_return_to, delete_return_to, safe_return_to, with_query_value, with_status
from ..services.notifications import status_message
from ..services.person_files import (
    PersonFilesError,
    open_person_folder,
    person_archive_filename,
    person_folder_image_items,
    person_folder_status,
)
from ..services.person_archive import PersonArchiveError, build_person_archive, save_person_archive
from ..services.photos import PhotoValidationError, photo_items
from ..services.person_create_drafts import (
    add_reward as add_draft_reward,
    cleanup_expired_drafts,
    clear_staged_photo,
    commit_draft,
    discard_draft,
    load_draft,
    new_draft_token,
    remove_reward as remove_draft_reward,
    staged_photo_path,
    stage_photo,
)
from ..services.save_dialog import SaveDialogCancelled, SaveDialogError, choose_save_path
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()
logger = logging.getLogger(__name__)
POST_CREATE_MESSAGE = "Кавалер создан. Добавьте фотографии и награды, затем нажмите «Сохранить»."


async def _read_form(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _person_create_context(
    settings,
    *,
    person,
    return_to: str,
    error: str | None,
    field_errors=None,
    draft_token: str = "",
    draft=None,
):
    reward_references = list_reward_references(settings.rewards_db_path) if settings.db_exists else []
    reference_names = {int(item["id_name"]): item["name"] for item in reward_references}
    draft = draft or {"rewards": [], "photos": {}}
    draft_rewards = [
        {**item, "name": reference_names.get(int(item.get("id_name") or 0), "—"), "index": index}
        for index, item in enumerate(draft.get("rewards", []))
    ]
    return {
        "settings": settings,
        "mode": "create",
        "person": person,
        "ranks": list_rank_guide(settings.rewards_db_path) if settings.db_exists else [],
        "photo_controls": photo_items("person", {}),
        "return_to": return_to,
        "error": error,
        "created_message": "",
        "birth_year_min": BIRTH_YEAR_MINIMUM,
        "birth_year_max": BIRTH_YEAR_MAXIMUM,
        "field_errors": field_errors or {},
        "draft_token": draft_token,
        "draft_rewards": draft_rewards,
        "draft_photos": draft.get("photos", {}),
        "reward_references": reward_references,
    }


def _write_error(exc: WriteBlockedError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


def _delete_validation_error(exc: PersonValidationError) -> HTTPException:
    status_code = 400 if str(exc) == "Действие требует подтверждения." else 404
    return HTTPException(status_code=status_code, detail=str(exc))


def _with_message(url: str, message: str) -> str:
    safe_url = safe_return_to(url)
    if not safe_url or not message:
        return safe_url
    parts = urlsplit(safe_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "message"]
    query.append(("message", message))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _person_created_edit_url(
    person_id: int,
    return_to: str = "",
    *,
    person_rank_id: int | None = None,
) -> str:
    safe_back = safe_return_to(return_to)
    if safe_back:
        parts = urlsplit(safe_back)
        query_values = parse_qs(parts.query, keep_blank_values=True)
        if parts.path.rstrip("/") == "/legacy" and query_values.get("tab", [""])[-1] == "rewards":
            safe_back = with_query_value(safe_back, "person_id", str(person_id))
            parts = urlsplit(safe_back)
            query = parse_qsl(parts.query, keep_blank_values=True)
            reward_filter_keys = {"country_id", "category_id", "subcategory_id", "name_id"}
            has_reward_filter = any(key in reward_filter_keys and value for key, value in query)
            rank_filter = next((value for key, value in reversed(query) if key == "rank_id" and value), "")
            hidden_filter_keys = reward_filter_keys if has_reward_filter else set()
            if person_rank_id is not None and rank_filter != str(person_rank_id):
                hidden_filter_keys = {*hidden_filter_keys, "rank_id"}
            if hidden_filter_keys:
                query = [(key, value) for key, value in query if key not in hidden_filter_keys]
                safe_back = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    query = [("created", "1")]
    if safe_back:
        query.append(("return_to", safe_back))
    return f"/persons/{person_id}/edit?{urlencode(query)}"


def _person_edit_context(
    settings,
    *,
    person: dict[str, object],
    return_to: str,
    error: str | None,
    post_create: bool,
    field_errors=None,
) -> dict[str, object]:
    safe_back = safe_return_to(return_to)
    person_id = int(person["id"])
    return {
        "settings": settings,
        "mode": "edit",
        "person": person,
        "ranks": list_rank_guide(settings.rewards_db_path) if settings.db_exists else [],
        "photo_controls": photo_items("person", person),
        "return_to": safe_back,
        "error": error,
        "created_message": POST_CREATE_MESSAGE if post_create else "",
        "birth_year_min": BIRTH_YEAR_MINIMUM,
        "birth_year_max": BIRTH_YEAR_MAXIMUM,
        "field_errors": field_errors or {},
        "post_create": post_create,
        "post_create_rewards": list_person_rewards(settings.rewards_db_path, person_id) if post_create else [],
        "post_create_url": _person_created_edit_url(person_id, safe_back) if post_create else "",
    }


def _person_detail_return_to(person_id: int, return_to: str = "") -> str:
    safe_back = safe_return_to(return_to)
    if not safe_back:
        return ""
    path = urlsplit(safe_back).path.rstrip("/")
    person_path = f"/persons/{person_id}"
    if path == person_path or path.startswith(f"{person_path}/"):
        return ""
    return safe_back


def _attachment_header(filename: str) -> str:
    safe_fallback = "".join(ch if ch.isascii() and ch not in {'"', "\\", ";"} else "_" for ch in filename) or "download"
    return f"attachment; filename=\"{safe_fallback}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/persons")
def persons_index(request: Request, page: int = 1, page_size: int = 25, status: str = ""):
    settings = get_settings()
    total = count_persons(settings.rewards_db_path) if settings.db_exists else 0
    pager = pagination(total, page, page_size)
    persons = (
        list_persons(settings.rewards_db_path, int(pager["page_size"]), int(pager["offset"]))
        if settings.db_exists
        else []
    )
    return templates.TemplateResponse(
        request,
        "persons.html",
        {
            "settings": settings,
            "persons": persons,
            "pagination": pager,
            "status_message": status_message(status),
        },
    )


@router.get("/persons/new")
def person_new(request: Request, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    cleanup_expired_drafts(settings)
    draft_token = new_draft_token()
    return templates.TemplateResponse(
        request,
        "person_form.html",
        _person_create_context(
            settings,
            person={},
            return_to=safe_return_to(return_to),
            error=None,
            draft_token=draft_token,
            draft=load_draft(settings, draft_token),
        ),
    )


@router.post("/persons/new")
async def person_create(request: Request):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    draft_token = str(form_values.get("draft_token") or "") or new_draft_token()
    try:
        data = person_data_from_mapping(form_values)
        person_id = commit_draft(settings, draft_token, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except (PersonValidationError, RewardValidationError, PhotoValidationError, ValueError, OSError) as exc:
        field = exc.field if isinstance(exc, PersonValidationError) else None
        return templates.TemplateResponse(
            request,
            "person_form.html",
            _person_create_context(
                settings,
                person=form_values,
                return_to=return_to,
                error=str(exc),
                field_errors={field: str(exc)} if field else {},
                draft_token=draft_token,
                draft=load_draft(settings, draft_token),
            ),
            status_code=400,
        )
    target = with_status(with_query_value(return_to or "/legacy?tab=rewards", "person_id", str(person_id)), "person_created")
    return RedirectResponse(target, status_code=303)


@router.post("/persons/new/draft/{draft_token}/rewards")
async def person_draft_reward_add(request: Request, draft_token: str):
    settings = get_settings()
    form = await request.form()
    try:
        draft = add_draft_reward(settings, draft_token, dict(form))
    except (ValueError, RewardValidationError) as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)
    reference_names = {
        int(item["id_name"]): item["name"] for item in list_reward_references(settings.rewards_db_path)
    }
    item = draft["rewards"][-1]
    return JSONResponse({
        "ok": True,
        "index": len(draft["rewards"]) - 1,
        "name": reference_names.get(int(item.get("id_name") or 0), "—"),
        "number": item.get("number"),
    })


@router.post("/persons/new/draft/{draft_token}/rewards/{index}/remove")
def person_draft_reward_remove(draft_token: str, index: int):
    settings = get_settings()
    try:
        remove_draft_reward(settings, draft_token, index)
    except ValueError as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=404)
    return JSONResponse({"ok": True})


@router.post("/persons/new/draft/{draft_token}/photos")
async def person_draft_photo_upload(request: Request, draft_token: str):
    settings = get_settings()
    form = await request.form()
    upload = form.get("file")
    if upload is None or not hasattr(upload, "read"):
        return JSONResponse({"ok": False, "message": "Выберите файл изображения."}, status_code=400)
    content = await upload.read(25 * 1024 * 1024 + 1)
    try:
        stage_photo(settings, draft_token, str(form.get("photo_field") or ""), upload.filename or "", content)
    except (ValueError, PhotoValidationError) as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)
    finally:
        await upload.close()
    field = str(form.get("photo_field") or "")
    return JSONResponse({"ok": True, "url": f"/persons/new/draft/{draft_token}/photos/{field}"})


@router.get("/persons/new/draft/{draft_token}/photos/{photo_field}")
def person_draft_photo_view(draft_token: str, photo_field: str):
    path = staged_photo_path(get_settings(), draft_token, photo_field)
    if path is None:
        raise HTTPException(status_code=404, detail="Фото черновика не найдено.")
    return FileResponse(path)


@router.post("/persons/new/draft/{draft_token}/photos/{photo_field}/clear")
def person_draft_photo_clear(draft_token: str, photo_field: str):
    try:
        clear_staged_photo(get_settings(), draft_token, photo_field)
    except (ValueError, PhotoValidationError) as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/persons/new/draft/{draft_token}/cancel")
async def person_draft_cancel(request: Request, draft_token: str):
    form_values = await _read_form(request)
    discard_draft(get_settings(), draft_token)
    return RedirectResponse(safe_return_to(form_values.get("return_to")) or "/legacy?tab=rewards", status_code=303)


@router.get("/persons/{person_id}")
def person_detail(request: Request, person_id: int, status: str = "", return_to: str = ""):
    settings = get_settings()
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Награжденный не найден.")
    rewards = list_person_rewards(settings.rewards_db_path, person_id)
    safe_back = _person_detail_return_to(person_id, return_to)
    person_folder, person_folder_exists = person_folder_status(settings, person_id)
    photos = person_photo_items(person, rewards)
    additional_photos = person_folder_image_items(settings, person_id, [photo.get("path") for photo in photos])
    return templates.TemplateResponse(
        request,
        "person_detail.html",
        {
            "settings": settings,
            "person": person,
            "rewards": rewards,
            "photos": photos,
            "additional_photos": additional_photos,
            "status_message": status_message(status),
            "return_to": safe_back,
            "person_folder_exists": person_folder_exists,
            "person_folder_name": person_folder.name,
            "person_archive_filename": person_archive_filename(str(person.get("fio") or "person"), person_id),
        },
    )


@router.get("/persons/{person_id}/booklet")
def person_booklet(request: Request, person_id: int, return_to: str = "", error: str = "", message: str = ""):
    settings = get_settings()
    safe_back = safe_return_to(return_to) or f"/persons/{person_id}"
    try:
        context = person_booklet_context(settings, person_id, safe_back)
    except BookletError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "person_booklet.html",
        {
            "settings": settings,
            **context,
            "return_to": safe_back,
            "pdf_filename": person_booklet_filename(settings, person_id),
            "error": error,
            "message": message,
            "error_message": error,
        },
    )


@router.post("/persons/{person_id}/booklet.pdf")
async def person_booklet_pdf(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to")) or f"/persons/{person_id}/booklet"
    if form_values.get("save_dialog") != "1":
        try:
            result = generate_person_booklet_pdf(settings, person_id)
        except BookletError as exc:
            context = person_booklet_context(settings, person_id, return_to)
            return templates.TemplateResponse(
                request,
                "person_booklet.html",
                {
                    "settings": settings,
                    **context,
                    "return_to": return_to,
                    "error": str(exc),
                    "message": "",
                    "error_message": str(exc),
                },
                status_code=400,
            )
        return FileResponse(result.path, media_type="application/pdf", filename=result.filename)
    try:
        target_path = choose_save_path(
            default_filename=person_booklet_filename(settings, person_id),
            title="Сохранить PDF-буклет",
            filetypes=(("PDF", "*.pdf"), ("Все файлы", "*.*")),
        )
    except SaveDialogCancelled:
        return RedirectResponse(_with_message(return_to, "Сохранение буклета отменено."), status_code=303)
    except SaveDialogError:
        logger.exception("Could not open booklet save dialog for person %s", person_id)
        return RedirectResponse(_with_message(return_to, "Не удалось открыть окно сохранения."), status_code=303)
    try:
        result = generate_person_booklet_pdf(settings, person_id, output_path=target_path)
    except BookletError as exc:
        context = person_booklet_context(settings, person_id, return_to)
        return templates.TemplateResponse(
            request,
            "person_booklet.html",
            {
                "settings": settings,
                **context,
                "return_to": return_to,
                "error": str(exc),
                "message": "",
                "error_message": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(_with_message(return_to, "Буклет сохранён."), status_code=303)


@router.get("/persons/{person_id}/edit")
def person_edit(request: Request, person_id: int, return_to: str = "", created: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Награжденный не найден.")
    return templates.TemplateResponse(
        request,
        "person_form.html",
        _person_edit_context(
            settings,
            person=person,
            return_to=return_to,
            error=None,
            post_create=created == "1",
        ),
    )


@router.post("/persons/{person_id}/edit")
async def person_update(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    post_create = str(form_values.get("post_create") or "") == "1"
    try:
        existing_person = get_person(settings.rewards_db_path, person_id)
        if existing_person is None:
            raise PersonValidationError("Награжденный не найден.")
        data = person_data_from_mapping(form_values, existing_birthday=existing_person.get("birthday"))
        update_person(settings, person_id, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except PersonValidationError as exc:
        person = {"id": person_id, **form_values}
        return templates.TemplateResponse(
            request,
            "person_form.html",
            _person_edit_context(
                settings,
                person=person,
                return_to=return_to,
                error=str(exc),
                post_create=post_create,
                field_errors={exc.field: str(exc)} if exc.field else {},
            ),
            status_code=400,
        )
    target = with_status(return_to, "person_updated") if return_to else f"/persons/{person_id}?status=person_updated"
    return RedirectResponse(target, status_code=303)


@router.post("/persons/{person_id}/delete")
async def person_delete(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    if form_values.get("delete_person_confirm") != "true" or form_values.get("confirm") != "true":
        raise _delete_validation_error(PersonValidationError("Действие требует подтверждения."))
    try:
        authorize_delete_execution(
            settings,
            "person",
            person_id,
            str(form_values.get("delete_operation_id") or ""),
        )
        result = delete_person_with_result(
            settings,
            person_id,
            confirm=form_values.get("confirm") == "true",
            operation_id=str(form_values.get("delete_operation_id") or ""),
        )
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except DeletePreflightValidationError:
        return RedirectResponse(
            delete_preflight_retry_return_to(return_to, f"/persons/{person_id}"),
            status_code=303,
        )
    except PersonDeleteBlockedError:
        blocked_return = delete_return_to(return_to)
        target = with_status(blocked_return, "person_delete_blocked") if blocked_return else f"/persons/{person_id}?status=person_delete_blocked"
        return RedirectResponse(target, status_code=303)
    except PersonValidationError as exc:
        raise _delete_validation_error(exc) from exc
    success_return = delete_return_to(return_to, "person_id")
    target = with_status(success_return, "person_deleted") if success_return else "/persons?status=person_deleted"
    if result.operation.warning_required:
        target = with_query_value(target, "media_cleanup", "failed")
    return RedirectResponse(target, status_code=303)


@router.post("/persons/{person_id}/open-folder")
async def person_open_folder(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to")) or f"/persons/{person_id}"
    ajax_request = request.headers.get("x-requested-with", "") == "XMLHttpRequest"
    if get_person(settings.rewards_db_path, person_id) is None:
        raise HTTPException(status_code=404, detail="Награжденный не найден.")
    try:
        open_person_folder(settings, person_id)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except PersonFilesError:
        if ajax_request:
            return JSONResponse(
                {"ok": False, "message": status_message("folder_missing")},
                status_code=404,
            )
        return RedirectResponse(with_status(return_to, "folder_missing"), status_code=303)
    if ajax_request:
        return JSONResponse({"ok": True, "message": status_message("folder_opened")})
    return RedirectResponse(with_status(return_to, "folder_opened"), status_code=303)


@router.post("/persons/{person_id}/archive-folder")
async def person_archive_folder(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to")) or f"/persons/{person_id}"
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Награжденный не найден.")
    try:
        target_path = choose_save_path(
            default_filename=person_archive_filename(str(person.get("fio") or "person"), person_id),
            title="Сохранить архив документов кавалера",
            filetypes=(("ZIP-архив", "*.zip"), ("Все файлы", "*.*")),
        )
    except SaveDialogCancelled:
        return RedirectResponse(with_status(return_to, "archive_cancelled"), status_code=303)
    except SaveDialogError:
        return RedirectResponse(with_status(return_to, "save_dialog_unavailable"), status_code=303)
    try:
        save_person_archive(settings, person_id, target_path)
    except PersonArchiveError:
        logger.exception("Could not build archive for person %s", person_id)
        return RedirectResponse(_with_message(return_to, "Не удалось создать архив."), status_code=303)
    except OSError:
        logger.exception("Could not write archive for person %s", person_id)
        return RedirectResponse(_with_message(return_to, "Не удалось записать архив."), status_code=303)
    return RedirectResponse(_with_message(return_to, "Архив создан."), status_code=303)


@router.post("/persons/{person_id}/archive-folder.zip")
async def person_archive_folder_zip(person_id: int):
    settings = get_settings()
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Награжденный не найден.")
    try:
        result = build_person_archive(settings, person_id)
    except PersonArchiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=result.content,
        media_type="application/zip",
        headers={"Content-Disposition": _attachment_header(result.filename)},
    )


@router.get("/persons/{person_id}/photos")
def person_photos(request: Request, person_id: int, index: int | None = None, return_to: str = ""):
    settings = get_settings()
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Награжденный не найден.")
    rewards = list_person_rewards(settings.rewards_db_path, person_id)
    photos = person_photo_items(person, rewards)
    photos.extend(person_folder_image_items(settings, person_id, [photo.get("path") for photo in photos]))
    available_photos = [photo for photo in photos if photo.get("path")]
    safe_back = safe_return_to(return_to)
    current_photo = None
    previous_index = None
    next_index = None
    if index is not None and available_photos:
        safe_index = max(0, min(index, len(available_photos) - 1))
        current_photo = available_photos[safe_index]
        previous_index = safe_index - 1 if safe_index > 0 else len(available_photos) - 1
        next_index = safe_index + 1 if safe_index < len(available_photos) - 1 else 0
    return templates.TemplateResponse(
        request,
        "person_photos.html",
        {
            "settings": settings,
            "person": person,
            "photos": photos,
            "available_photos": available_photos,
            "current_photo": current_photo,
            "previous_index": previous_index,
            "next_index": next_index,
            "return_to": safe_back,
        },
    )
