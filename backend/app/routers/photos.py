from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.datastructures import UploadFile

from ..config import get_settings
from ..services.photos import MAX_PHOTO_BYTES, PhotoValidationError, clear_photo, save_photo
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()


def _safe_return_url(value: object, default: str = "/") -> str:
    text = str(value or "").strip()
    if text.startswith("/") and not text.startswith("//"):
        return text
    return default


async def _read_urlencoded(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


@router.get("/photo/view")
def photo_view(request: Request, path: str = "", label: str = "", back: str = "/"):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "photo_view.html",
        {
            "settings": settings,
            "path": path,
            "label": label or "Фото",
            "back": _safe_return_url(back),
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
    return_url = _safe_return_url(form.get("return_url"))
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
    return_url = _safe_return_url(form.get("return_url"))
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
