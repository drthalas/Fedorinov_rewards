from fastapi import APIRouter, HTTPException, Request

from ..config import get_settings
from ..repositories.persons import count_persons, get_person, list_person_rewards, list_persons, person_photo_items
from ..services.display import pagination
from .templates import templates


router = APIRouter()


@router.get("/persons")
def persons_index(request: Request, page: int = 1, page_size: int = 25):
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
        {"settings": settings, "persons": persons, "pagination": pager},
    )


@router.get("/persons/{person_id}")
def person_detail(request: Request, person_id: int):
    settings = get_settings()
    person = get_person(settings.rewards_db_path, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    rewards = list_person_rewards(settings.rewards_db_path, person_id)
    return templates.TemplateResponse(
        request,
        "person_detail.html",
        {"settings": settings, "person": person, "rewards": rewards},
    )


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
