from fastapi import APIRouter

from ..config import get_settings
from ..services.update_checker import check_for_updates
from ..version import APP_NAME, APP_VERSION


router = APIRouter()


@router.get("/version")
def version_info() -> dict[str, str]:
    return {
        "app_name": APP_NAME,
        "version": APP_VERSION,
    }


@router.get("/updates/check")
def updates_check() -> dict[str, object]:
    return check_for_updates(get_settings())
