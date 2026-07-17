from datetime import date
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from urllib.parse import parse_qs, urlencode

from ..config import get_settings
from ..repositories.guides import guide_cascade_data, guide_cascade_options
from ..repositories.persons import get_person
from ..repositories.rewards import get_reward, reward_photo_items
from ..repositories.rewards_write import (
    RewardValidationError,
    check_reward_duplicate,
    create_reward,
    delete_reward_with_result,
    reward_data_from_mapping,
    reward_delete_confirmation_message,
    reward_delete_preview,
    reward_duplicate_message,
    update_reward,
)
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


def _reward_created_edit_url(reward_id: int, return_to: str = "") -> str:
    query = [("created", "1")]
    if return_to:
        query.append(("return_to", return_to))
    return f"/rewards/{reward_id}/edit?{urlencode(query)}"


def _reward_display_name(reward: dict[str, object]) -> str:
    return str(reward.get("name") or "").strip()


def _reward_heading(reward: dict[str, object]) -> str:
    reward_name = _reward_display_name(reward)
    return f"Награда: {reward_name}" if reward_name else "Награда"


def _reward_legacy_back_url(reward: dict[str, object]) -> str:
    person_id = _safe_int(reward.get("person_id"))
    return f"/legacy?tab=rewards&person_id={person_id}" if person_id is not None else "/legacy?tab=rewards"


@router.get("/rewards/check-duplicate")
def reward_duplicate_check(id_name: str = "", number: str = "", current_reward_id: str = ""):
    settings = get_settings()
    raw_number = str(number or "").strip()
    name_id = _safe_int(id_name)
    reward_number = _safe_int(raw_number)
    current_id = _safe_int(current_reward_id)

    if not settings.db_exists:
        return {"duplicate": False, "message": ""}
    if not raw_number:
        return {"duplicate": False, "message": ""}
    if name_id is None:
        return {"duplicate": False, "message": "Выберите наименование награды для проверки номера"}
    if reward_number is None:
        return {"duplicate": False, "message": "Укажите корректный номер награды."}
    duplicate = check_reward_duplicate(settings, name_id, reward_number, current_id)
    if not duplicate:
        return {"duplicate": False, "message": "Номер свободен"}
    return {
        "duplicate": True,
        "message": reward_duplicate_message(duplicate),
        **duplicate,
    }


@router.get("/persons/{person_id}/rewards/new")
def reward_new(request: Request, person_id: int, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Награжденный не найден.")
    reward = {"person_id": person_id, "instock": False, "date_purchase": date.today().isoformat()}
    return templates.TemplateResponse(
        request,
        "reward_form.html",
        {
            "settings": settings,
            "mode": "create",
            "person": person,
            "reward": reward,
            "guides": _guide_options(settings),
            "guide_cascade": _guide_cascade(settings),
            "photo_controls": [],
            "return_to": safe_return_to(return_to),
            "error": None,
            "created_message": "",
        },
    )


@router.post("/persons/{person_id}/rewards/new")
async def reward_create(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        data = reward_data_from_mapping(form_values)
        reward_id = create_reward(settings, person_id, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except RewardValidationError as exc:
        person = get_person(settings.rewards_db_path, person_id)
        return templates.TemplateResponse(
            request,
            "reward_form.html",
            {
                "settings": settings,
                "mode": "create",
                "person": person,
                "reward": {"person_id": person_id, **form_values},
                "guides": _guide_options(settings, form_values),
                "guide_cascade": _guide_cascade(settings),
                "photo_controls": [],
                "return_to": return_to,
                "error": str(exc),
                "created_message": "",
            },
            status_code=400,
        )
    target = _reward_created_edit_url(reward_id, return_to or f"/persons/{person_id}")
    return RedirectResponse(target, status_code=303)


@router.get("/rewards/{reward_id}")
def reward_detail(request: Request, reward_id: int, status: str = "", return_to: str = ""):
    settings = get_settings()
    reward = get_reward(settings.rewards_db_path, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="Награда не найдена.")
    delete_preview = reward_delete_preview(settings, reward_id)
    safe_back = safe_return_to(return_to)
    return templates.TemplateResponse(
        request,
        "reward_detail.html",
        {
            "settings": settings,
            "reward": reward,
            "reward_name": _reward_display_name(reward),
            "reward_heading": _reward_heading(reward),
            "reward_back_url": safe_back or _reward_legacy_back_url(reward),
            "photos": reward_photo_items(reward),
            "status_message": status_message(status),
            "return_to": safe_back,
            "delete_operation_id": uuid4().hex,
            "delete_confirmation": reward_delete_confirmation_message(delete_preview),
            "delete_blocked": delete_preview.media.block_reason is not None,
        },
    )


@router.get("/rewards/{reward_id}/edit")
def reward_edit(request: Request, reward_id: int, return_to: str = "", created: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    reward = get_reward(settings.rewards_db_path, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="Награда не найдена.")
    person = get_person(settings.rewards_db_path, int(reward["person_id"]))
    return templates.TemplateResponse(
        request,
        "reward_form.html",
        {
            "settings": settings,
            "mode": "edit",
            "person": person,
            "reward": reward,
            "guides": _guide_options(settings, reward),
            "guide_cascade": _guide_cascade(settings),
            "photo_controls": photo_items("reward", reward),
            "return_to": safe_return_to(return_to),
            "error": None,
            "created_message": "Награда добавлена. Теперь можно добавить фотографии и документы." if created == "1" else "",
        },
    )


@router.post("/rewards/{reward_id}/edit")
async def reward_update(request: Request, reward_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        data = reward_data_from_mapping(form_values)
        update_reward(settings, reward_id, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except RewardValidationError as exc:
        reward = get_reward(settings.rewards_db_path, reward_id) or {"id": reward_id}
        person_id = int(reward.get("person_id") or 0)
        person = get_person(settings.rewards_db_path, person_id) if person_id else None
        return templates.TemplateResponse(
            request,
            "reward_form.html",
            {
                "settings": settings,
                "mode": "edit",
                "person": person,
                "reward": {**reward, **form_values},
                "guides": _guide_options(settings, {**reward, **form_values}),
                "guide_cascade": _guide_cascade(settings),
                "photo_controls": photo_items("reward", reward),
                "return_to": return_to,
                "error": str(exc),
                "created_message": "",
            },
            status_code=400,
        )
    target = with_status(return_to, "reward_updated") if return_to else f"/rewards/{reward_id}?status=reward_updated"
    return RedirectResponse(target, status_code=303)


@router.post("/rewards/{reward_id}/delete")
async def reward_delete(request: Request, reward_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    if form_values.get("delete_reward_confirm") != "true" or form_values.get("confirm") != "true":
        raise HTTPException(status_code=400, detail="Действие требует подтверждения.")
    try:
        result = delete_reward_with_result(
            settings,
            reward_id,
            confirm=True,
            operation_id=str(form_values.get("delete_operation_id") or ""),
        )
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except RewardValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    success_return = delete_return_to(return_to)
    target = with_status(success_return, "reward_deleted") if success_return else f"/persons/{result.person_id}?status=reward_deleted"
    if result.operation.warning_required:
        target = with_query_value(target, "media_cleanup", "failed")
    return RedirectResponse(target, status_code=303)
