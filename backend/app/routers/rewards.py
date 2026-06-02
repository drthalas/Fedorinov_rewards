from fastapi import APIRouter, HTTPException, Request

from ..config import get_settings
from ..repositories.rewards import get_reward, reward_photo_items
from .templates import templates


router = APIRouter()


@router.get("/rewards/{reward_id}")
def reward_detail(request: Request, reward_id: int):
    settings = get_settings()
    reward = get_reward(settings.rewards_db_path, reward_id)
    if reward is None:
        raise HTTPException(status_code=404, detail="Reward not found")
    return templates.TemplateResponse(
        request,
        "reward_detail.html",
        {"settings": settings, "reward": reward, "photos": reward_photo_items(reward)},
    )
