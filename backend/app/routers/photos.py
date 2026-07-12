from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.datastructures import UploadFile

from ..config import get_settings
from ..services.navigation import safe_return_to
from ..services.photos import (
    MAX_PHOTO_BYTES,
    PhotoValidationError,
    clear_photo,
    create_person_media,
    delete_person_media,
    save_photo,
    update_person_media,
)
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()


async def _read_urlencoded(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


@router.get("/photo/view")
def photo_view(request: Request, path: str = "", label: str = "", back: str = "/", return_to: str = ""):
    settings = get_settings()
    safe_back = safe_return_to(return_to) or safe_return_to(back, "/")
    return templates.TemplateResponse(
        request,
        "photo_view.html",
        {
            "settings": settings,
            "path": path,
            "label": label or "Фото",
            "return_to": safe_back,
        },
    )


@router.post("/photos/upload")
async def photo_upload(request: Request):
    settings = get_settings()
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Multipart form data is required") from exc

    entity_type = str(form.get("entity_type") or "")
    photo_field = str(form.get("photo_field") or "")
    return_url = safe_return_to(form.get("return_to")) or safe_return_to(form.get("return_url"), "/")
    try:
        entity_id = int(str(form.get("entity_id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid entity_id") from exc

    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=400, detail="File is required")
    content = await upload.read(MAX_PHOTO_BYTES + 1)

    try:
        save_photo(settings, entity_type, entity_id, photo_field, upload.filename or "", content)
    except WriteBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PhotoValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await upload.close()

    return RedirectResponse(return_url, status_code=303)


@router.post("/photos/clear")
async def photo_clear(request: Request):
    settings = get_settings()
    form = await _read_urlencoded(request)
    entity_type = str(form.get("entity_type") or "")
    photo_field = str(form.get("photo_field") or "")
    return_url = safe_return_to(form.get("return_to")) or safe_return_to(form.get("return_url"), "/")
    try:
        entity_id = int(str(form.get("entity_id") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid entity_id") from exc

    try:
        clear_photo(settings, entity_type, entity_id, photo_field)
    except WriteBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PhotoValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return RedirectResponse(return_url, status_code=303)


def _person_media_return_url(person_id: int, value: object) -> str:
    return safe_return_to(value, f"/persons/{person_id}/edit")


@router.post("/persons/{person_id}/media/create")
async def person_media_create(request: Request, person_id: int):
    settings = get_settings()
    form = await _read_urlencoded(request)
    return_url = _person_media_return_url(person_id, form.get("return_url"))
    try:
        create_person_media(settings, person_id, form.get("title"), form.get("description"))
    except WriteBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PhotoValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(return_url, status_code=303)


@router.post("/persons/{person_id}/media/update")
async def person_media_update(request: Request, person_id: int):
    settings = get_settings()
    form = await _read_urlencoded(request)
    return_url = _person_media_return_url(person_id, form.get("return_url"))
    raw_media_id = str(form.get("media_id") or "").strip()
    try:
        media_id = int(raw_media_id) if raw_media_id else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid media_id") from exc
    try:
        update_person_media(
            settings,
            person_id,
            form.get("title"),
            form.get("description"),
            media_id=media_id,
            photo_field=str(form.get("photo_field") or ""),
        )
    except WriteBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PhotoValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(return_url, status_code=303)


@router.post("/persons/{person_id}/media/{media_id}/delete")
async def person_media_delete(request: Request, person_id: int, media_id: int):
    settings = get_settings()
    form = await _read_urlencoded(request)
    return_url = _person_media_return_url(person_id, form.get("return_url"))
    if str(form.get("confirm") or "").lower() != "true":
        raise HTTPException(status_code=400, detail="Действие требует подтверждения.")
    try:
        delete_person_media(settings, person_id, media_id)
    except WriteBlockedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PhotoValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(return_url, status_code=303)
