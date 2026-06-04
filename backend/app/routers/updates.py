from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from urllib.parse import parse_qs

from ..config import get_settings
from ..services.update_checker import check_for_updates
from ..services.updater import UpdateError, apply_update, read_update_status
from ..version import APP_NAME, APP_VERSION
from .templates import templates


router = APIRouter()


@router.get("/version")
def version_info() -> dict[str, str]:
    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
    }


@router.get("/updates/check")
def updates_check() -> dict[str, object]:
    return check_for_updates(get_settings())


@router.get("/updates/status")
def updates_status() -> dict[str, object]:
    return read_update_status(get_settings())


async def _read_form(request: Request) -> dict[str, str]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


@router.post("/updates/apply")
async def updates_apply(request: Request):
    settings = get_settings()
    form_values = await _read_form(request)
    wants_json = "application/json" in request.headers.get("accept", "")
    confirmed = str(form_values.get("confirm_update") or "").lower() in {"true", "on", "1", "yes"}
    if not confirmed:
        detail = "Подтвердите обновление перед установкой."
        if wants_json:
            return JSONResponse({"ok": False, "error": detail}, status_code=400)
        raise HTTPException(status_code=400, detail=detail)

    try:
        result = apply_update(settings, dry_run=False)
    except UpdateError as exc:
        result = {"ok": False, "error": str(exc), "message": str(exc)}

    if wants_json:
        status_code = 200 if result.get("ok") else 400
        return JSONResponse(result, status_code=status_code)
    return templates.TemplateResponse(request, "update_result.html", {"settings": settings, "result": result})
