from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
import logging
from urllib.parse import parse_qs, parse_qsl, quote, urlencode, urlsplit, urlunsplit

from ..config import get_settings
from ..repositories.guides import list_rank_guide
from ..repositories.persons import count_persons, get_person, list_person_rewards, list_persons, person_photo_items
from ..repositories.persons_write import (
    PersonDeleteBlockedError,
    PersonValidationError,
    create_person,
    delete_person,
    person_data_from_mapping,
    update_person,
)
from ..services.display import pagination
from ..services.booklets import BookletError, generate_person_booklet_pdf, person_booklet_context, person_booklet_filename
from ..services.navigation import safe_return_to, with_status
from ..services.notifications import status_message
from ..services.person_files import (
    PersonFilesError,
    open_person_folder,
    person_archive_filename,
    person_folder_image_items,
    person_folder_status,
)
from ..services.person_archive import PersonArchiveError, build_person_archive, save_person_archive
from ..services.photos import photo_items
from ..services.save_dialog import SaveDialogCancelled, SaveDialogError, choose_save_path
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()
logger = logging.getLogger(__name__)


async def _read_form(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


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


def _person_created_edit_url(person_id: int, return_to: str = "") -> str:
    query = [("created", "1")]
    if return_to:
        query.append(("return_to", return_to))
    return f"/persons/{person_id}/edit?{urlencode(query)}"


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
    ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
    return templates.TemplateResponse(
        request,
        "person_form.html",
        {
            "settings": settings,
            "mode": "create",
            "person": {},
            "ranks": ranks,
            "photo_controls": [],
            "return_to": safe_return_to(return_to),
            "error": None,
            "created_message": "",
        },
    )


@router.post("/persons/new")
async def person_create(request: Request):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        data = person_data_from_mapping(form_values)
        person_id = create_person(settings, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except PersonValidationError as exc:
        ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
        return templates.TemplateResponse(
            request,
            "person_form.html",
            {
                "settings": settings,
                "mode": "create",
                "person": form_values,
                "ranks": ranks,
                "photo_controls": [],
                "return_to": return_to,
                "error": str(exc),
                "created_message": "",
            },
            status_code=400,
        )
    target = _person_created_edit_url(person_id, return_to)
    return RedirectResponse(target, status_code=303)


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
    ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
    return templates.TemplateResponse(
        request,
        "person_form.html",
        {
            "settings": settings,
            "mode": "edit",
            "person": person,
            "ranks": ranks,
            "photo_controls": photo_items("person", person),
            "return_to": safe_return_to(return_to),
            "error": None,
            "created_message": "Кавалер создан. Теперь можно добавить фотографии и документы." if created == "1" else "",
        },
    )


@router.post("/persons/{person_id}/edit")
async def person_update(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        data = person_data_from_mapping(form_values)
        update_person(settings, person_id, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except PersonValidationError as exc:
        ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
        person = {"id": person_id, **form_values}
        return templates.TemplateResponse(
            request,
            "person_form.html",
            {
                "settings": settings,
                "mode": "edit",
                "person": person,
                "ranks": ranks,
                "photo_controls": photo_items("person", person),
                "return_to": return_to,
                "error": str(exc),
                "created_message": "",
            },
            status_code=400,
        )
    target = with_status(return_to, "person_updated") if return_to else f"/persons/{person_id}?status=person_updated"
    return RedirectResponse(target, status_code=303)


@router.post("/persons/{person_id}/delete")
async def person_delete(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    if form_values.get("delete_person_confirm") != "true":
        raise _delete_validation_error(PersonValidationError("Действие требует подтверждения."))
    try:
        delete_person(settings, person_id, confirm=form_values.get("confirm") == "true")
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except PersonDeleteBlockedError:
        target = with_status(return_to, "delete_blocked") if return_to else f"/persons/{person_id}?status=delete_blocked"
        return RedirectResponse(target, status_code=303)
    except PersonValidationError as exc:
        raise _delete_validation_error(exc) from exc
    target = with_status(return_to, "person_deleted") if return_to else "/persons?status=person_deleted"
    return RedirectResponse(target, status_code=303)


@router.post("/persons/{person_id}/open-folder")
async def person_open_folder(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to")) or f"/persons/{person_id}"
    try:
        open_person_folder(settings, person_id)
    except PersonFilesError:
        return RedirectResponse(with_status(return_to, "folder_missing"), status_code=303)
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
