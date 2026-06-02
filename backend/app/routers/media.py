from fastapi import APIRouter
from fastapi.responses import Response
import mimetypes
import subprocess

from ..config import get_settings
from ..services.media import fallback_image, resolve_media_path


router = APIRouter()
READ_TIMEOUT_SECONDS = 3


def _content_type(path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _read_bytes(path) -> bytes | None:
    try:
        result = subprocess.run(
            ["/bin/cat", str(path)],
            capture_output=True,
            check=True,
            timeout=READ_TIMEOUT_SECONDS,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    return result.stdout


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
    resolved = resolve_media_path(settings, path)
    if resolved is None:
        return _placeholder()

    content = _read_bytes(resolved)
    if content is not None:
        return Response(content=content, media_type=_content_type(resolved))

    fallback = fallback_image(settings)
    if fallback is not None and fallback != resolved:
        content = _read_bytes(fallback)
        if content is not None:
            return Response(content=content, media_type=_content_type(fallback))

    return _placeholder()


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
