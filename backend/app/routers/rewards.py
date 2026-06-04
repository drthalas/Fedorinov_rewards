from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from urllib.parse import parse_qs

from ..config import get_settings
from ..repositories.guides import list_guide_level
from ..repositories.persons import get_person
from ..repositories.rewards import get_reward, reward_photo_items
from ..repositories.rewards_write import (
    RewardValidationError,
    create_reward,
    delete_reward,
    reward_data_from_mapping,
    update_reward,
)
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


def _guide_options(settings):
    if not settings.db_exists:
        return {"gos": [], "categories": [], "subcategories": [], "names": []}
    return {
        "gos": list_guide_level(settings.rewards_db_path, 0),
        "categories": list_guide_level(settings.rewards_db_path, 1),
        "subcategories": list_guide_level(settings.rewards_db_path, 2),
        "names": list_guide_level(settings.rewards_db_path, 3),
    }


@router.get("/persons/{person_id}/rewards/new")
def reward_new(request: Request, person_id: int):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="WRITE_MODE=true is required for changes")
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    reward = {"person_id": person_id, "instock": False}
    return templates.TemplateResponse(
        request,
        "reward_form.html",
        {
            "settings": settings,
            "mode": "create",
            "person": person,
            "reward": reward,
            "guides": _guide_options(settings),
            "photo_controls": [],
            "error": None,
        },
    )


@router.post("/persons/{person_id}/rewards/new")
async def reward_create(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
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
                "guides": _guide_options(settings),
                "photo_controls": [],
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(f"/persons/{person_id}?status=reward_created", status_code=303)


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
def reward_edit(request: Request, reward_id: int):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="WRITE_MODE=true is required for changes")
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
            "guides": _guide_options(settings),
            "photo_controls": photo_items("reward", reward),
            "error": None,
        },
    )


@router.post("/rewards/{reward_id}/edit")
async def reward_update(request: Request, reward_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
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
                "guides": _guide_options(settings),
                "photo_controls": photo_items("reward", reward),
                "error": str(exc),
            },
            status_code=400,
        )
    return RedirectResponse(f"/rewards/{reward_id}?status=updated", status_code=303)


@router.post("/rewards/{reward_id}/delete")
async def reward_delete(request: Request, reward_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
    try:
        person_id = delete_reward(settings, reward_id, confirm=form_values.get("confirm") == "true")
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except RewardValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(f"/persons/{person_id}?status=reward_deleted", status_code=303)
