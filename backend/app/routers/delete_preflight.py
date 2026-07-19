from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..services.delete_preflight import DeletePreflightError, DeletePreflightNotFoundError, issue_delete_preflight


router = APIRouter()


@router.get("/delete-preflight/{entity_type}/{entity_id}")
def delete_preflight(entity_type: str, entity_id: int):
    settings = get_settings()
    if not settings.write_mode:
        raise HTTPException(status_code=403, detail="Редактирование выключено.")
    try:
        return issue_delete_preflight(settings, entity_type, entity_id)
    except DeletePreflightNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DeletePreflightError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
