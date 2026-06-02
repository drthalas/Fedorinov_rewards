from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import get_settings
from ..services.media import resolve_media_path


router = APIRouter()


@router.get("/media")
def media(path: str = ""):
    settings = get_settings()
    resolved = resolve_media_path(settings, path)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Media fallback is not available")
    return FileResponse(resolved)
