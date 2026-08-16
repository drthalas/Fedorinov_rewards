from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..config import get_settings
from ..services.media_optimization_workflow import (
    MediaOptimizationWorkflowError,
    activate_optimized_workspace,
    activate_source_workspace,
    cancel_operation,
    start_check,
    start_optimize,
    workflow_snapshot,
)
from ..services.write_guard import WriteBlockedError, ensure_write_allowed
from .templates import templates


router = APIRouter(prefix="/maintenance/media-optimization")


def _redirect(status: str = "", error: str = "") -> RedirectResponse:
    query: list[str] = []
    if status:
        query.append(f"status={status}")
    if error:
        query.append(f"error={error}")
    suffix = "?" + urlencode(dict(item.split("=", 1) for item in query)) if query else ""
    return RedirectResponse(f"/maintenance/media-optimization{suffix}", status_code=303)


@router.get("")
def media_optimization_page(request: Request, status: str = "", error: str = ""):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "media_optimization.html",
        {
            "settings": settings,
            "snapshot": workflow_snapshot(settings),
            "status_message": status,
            "error_message": error,
        },
    )


@router.get("/status")
def media_optimization_status() -> JSONResponse:
    return JSONResponse(workflow_snapshot(get_settings()))


@router.post("/check")
def media_optimization_check() -> RedirectResponse:
    settings = get_settings()
    try:
        start_check(settings)
    except MediaOptimizationWorkflowError as exc:
        return _redirect(error=str(exc))
    return _redirect(status="Проверка запущена.")


@router.post("/optimize")
async def media_optimization_optimize(request: Request) -> RedirectResponse:
    settings = get_settings()
    try:
        ensure_write_allowed(settings)
        form = await request.form()
        snapshot = workflow_snapshot(settings)
        if not snapshot["target_complete"] and str(form.get("confirm_separate_copy") or "").lower() != "true":
            raise MediaOptimizationWorkflowError("Подтвердите создание отдельной optimized copy")
        restart = str(form.get("restart") or "").lower() == "true"
        start_optimize(settings, restart_incomplete=restart)
    except (MediaOptimizationWorkflowError, WriteBlockedError, ValueError) as exc:
        return _redirect(error=str(exc))
    return _redirect(status="Оптимизация запущена.")


@router.post("/cancel")
def media_optimization_cancel() -> RedirectResponse:
    if not cancel_operation(get_settings()):
        return _redirect(error="Активная операция не найдена.")
    return _redirect(status="Остановка запрошена. Текущий файл будет завершён безопасно.")


@router.post("/activate")
def media_optimization_activate() -> RedirectResponse:
    settings = get_settings()
    try:
        ensure_write_allowed(settings)
        activate_optimized_workspace(settings)
    except (MediaOptimizationWorkflowError, WriteBlockedError, ValueError) as exc:
        return _redirect(error=str(exc))
    return _redirect(status="Проверенная optimized copy активирована.")


@router.post("/activate-source")
def media_optimization_activate_source() -> RedirectResponse:
    settings = get_settings()
    try:
        ensure_write_allowed(settings)
        activate_source_workspace(settings)
    except (WriteBlockedError, ValueError) as exc:
        return _redirect(error=str(exc))
    return _redirect(status="Активна исходная рабочая копия.")
