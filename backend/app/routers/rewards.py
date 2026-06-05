from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from urllib.parse import parse_qs

from ..config import get_settings
from ..repositories.guides import guide_cascade_data, guide_cascade_options
from ..repositories.persons import get_person
from ..repositories.rewards import get_reward, reward_photo_items
from ..repositories.rewards_write import (
    RewardValidationError,
    create_reward,
    delete_reward,
    reward_data_from_mapping,
    update_reward,
)
from ..services.navigation import safe_return_to, with_status
from ..services.photos import photo_items
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()


STATUS_MESSAGES = {
    "created": "Награда добавлена.",
    "updated": "Изменения сохранены.",
    "deleted": "Награда удалена.",
}


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


@router.get("/persons/{person_id}/rewards/new")
def reward_new(request: Request, person_id: int, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
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
        },
    )


@router.post("/persons/{person_id}/rewards/new")
async def reward_create(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        data = reward_data_from_mapping(form_values)
        create_reward(settings, person_id, data)
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
            },
            status_code=400,
        )
    target = with_status(return_to, "reward_created") if return_to else f"/persons/{person_id}?status=reward_created"
    return RedirectResponse(target, status_code=303)


@router.get("/rewards/{reward_id}")
def reward_detail(request: Request, reward_id: int, status: str = ""):
    settings = get_settings()
    reward = get_reward(settings.rewards_db_path, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="Reward not found")
    return templates.TemplateResponse(
        request,
        "reward_detail.html",
        {
            "settings": settings,
            "reward": reward,
            "photos": reward_photo_items(reward),
            "status_message": STATUS_MESSAGES.get(status),
        },
    )


@router.get("/rewards/{reward_id}/edit")
def reward_edit(request: Request, reward_id: int, return_to: str = ""):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    reward = get_reward(settings.rewards_db_path, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="Reward not found")
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
            },
            status_code=400,
        )
    target = with_status(return_to, "updated") if return_to else f"/rewards/{reward_id}?status=updated"
    return RedirectResponse(target, status_code=303)


@router.post("/rewards/{reward_id}/delete")
async def reward_delete(request: Request, reward_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    return_to = safe_return_to(form_values.get("return_to"))
    try:
        person_id = delete_reward(settings, reward_id, confirm=form_values.get("confirm") == "true")
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except RewardValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target = with_status(return_to, "reward_deleted") if return_to else f"/persons/{person_id}?status=reward_deleted"
    return RedirectResponse(target, status_code=303)
