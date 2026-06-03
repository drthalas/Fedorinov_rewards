from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from urllib.parse import parse_qs

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
from ..services.write_guard import WriteBlockedError
from .templates import templates


router = APIRouter()


STATUS_MESSAGES = {
    "created": "Награжденный добавлен.",
    "updated": "Изменения сохранены.",
    "deleted": "Награжденный удален.",
    "delete_blocked": "Нельзя удалить: у награжденного есть награды. Сначала удалите или перенесите награды.",
    "reward_created": "Награда добавлена.",
    "reward_deleted": "Награда удалена.",
}


async def _read_form(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _write_error(exc: WriteBlockedError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


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
            "status_message": STATUS_MESSAGES.get(status),
        },
    )


@router.get("/persons/new")
def person_new(request: Request):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="WRITE_MODE=true is required for changes")
    ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
    return templates.TemplateResponse(
        request,
        "person_form.html",
        {"settings": settings, "mode": "create", "person": {}, "ranks": ranks, "error": None},
    )


@router.post("/persons/new")
async def person_create(request: Request):
    settings = get_settings()
    try:
        data = person_data_from_mapping(await _read_form(request))
        person_id = create_person(settings, data)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except PersonValidationError as exc:
        ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
        form_values = await _read_form(request)
        return templates.TemplateResponse(
            request,
            "person_form.html",
            {"settings": settings, "mode": "create", "person": form_values, "ranks": ranks, "error": str(exc)},
            status_code=400,
        )
    return RedirectResponse(f"/persons/{person_id}?status=created", status_code=303)


@router.get("/persons/{person_id}")
def person_detail(request: Request, person_id: int, status: str = ""):
    settings = get_settings()
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    rewards = list_person_rewards(settings.rewards_db_path, person_id)
    return templates.TemplateResponse(
        request,
        "person_detail.html",
        {"settings": settings, "person": person, "rewards": rewards, "status_message": STATUS_MESSAGES.get(status)},
    )


@router.get("/persons/{person_id}/edit")
def person_edit(request: Request, person_id: int):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="WRITE_MODE=true is required for changes")
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    ranks = list_rank_guide(settings.rewards_db_path) if settings.db_exists else []
    return templates.TemplateResponse(
        request,
        "person_form.html",
        {"settings": settings, "mode": "edit", "person": person, "ranks": ranks, "error": None},
    )


@router.post("/persons/{person_id}/edit")
async def person_update(request: Request, person_id: int):
    settings = get_settings()
    form_values = await _read_form(request)
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
            {"settings": settings, "mode": "edit", "person": person, "ranks": ranks, "error": str(exc)},
            status_code=400,
        )
    return RedirectResponse(f"/persons/{person_id}?status=updated", status_code=303)


@router.post("/persons/{person_id}/delete")
def person_delete(request: Request, person_id: int):
    settings = get_settings()
    try:
        delete_person(settings, person_id)
    except WriteBlockedError as exc:
        raise _write_error(exc) from exc
    except PersonDeleteBlockedError:
        return RedirectResponse(f"/persons/{person_id}?status=delete_blocked", status_code=303)
    except PersonValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RedirectResponse("/persons?status=deleted", status_code=303)


@router.get("/persons/{person_id}/photos")
def person_photos(request: Request, person_id: int):
    settings = get_settings()
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    rewards = list_person_rewards(settings.rewards_db_path, person_id)
    photos = person_photo_items(person, rewards)
    return templates.TemplateResponse(
        request,
        "person_photos.html",
        {"settings": settings, "person": person, "photos": photos},
    )
