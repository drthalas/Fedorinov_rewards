from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
import mimetypes

from ..config import get_settings
from ..services.media import resolve_media, resolve_media_path


router = APIRouter()


def _content_type(path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _placeholder() -> Response:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240" viewBox="0 0 320 240">'
        '<rect width="320" height="240" fill="#eef2f6"/>'
        '<text x="160" y="122" text-anchor="middle" font-family="Arial" font-size="18" fill="#475467">'
        "no photo"
        "</text></svg>"
    )
    return Response(content=svg, media_type="image/svg+xml")


@router.get("/media")
def media(path: str = ""):
    settings = get_settings()
    resolution = resolve_media(settings, path)
    if not resolution.serving_path:
        return _placeholder()
    return FileResponse(resolution.serving_path, media_type=_content_type(resolution.serving_path))


@router.head("/media")
def media_head(path: str = ""):
    settings = get_settings()
    resolved = resolve_media_path(settings, path)
    if resolved is None:
        return Response(status_code=404)
    return Response(
        media_type=_content_type(resolved),
        headers={"content-length": str(resolved.stat().st_size)},
    )


@router.get("/media-debug")
def media_debug(path: str = ""):
    settings = get_settings()
    return resolve_media(settings, path).as_dict()
