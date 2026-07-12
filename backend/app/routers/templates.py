from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

from ..config import PROJECT_ROOT, get_settings
from ..services.display import (
    bool_class,
    dash_if_empty,
    format_bool,
    format_birth_year,
    format_date,
    format_money,
    has_media_path,
    safe_external_url,
)
from ..services.dates import format_birth_year_input, format_date_input
from ..services.media import resolve_media_path


templates = Jinja2Templates(directory=PROJECT_ROOT / "backend" / "app" / "templates")


STATIC_ASSET_VERSION = "20260712-cavaliers-design-4"


def static_url(path: str) -> str:
    return str(URL(path=f"/static/{path}").include_query_params(v=STATIC_ASSET_VERSION))


def media_url(path: object) -> str:
    value = path if isinstance(path, str) else ""
    return str(URL(path="/media").include_query_params(path=value))


def photo_view_url(path: object, label: object = "", return_to: object = "") -> str:
    value = path if isinstance(path, str) else ""
    query = {"path": value}
    if isinstance(label, str) and label:
        query["label"] = label
    if isinstance(return_to, str) and return_to.startswith("/"):
        query["return_to"] = return_to
    return str(URL(path="/photo/view").include_query_params(**query))


def media_exists(path: object) -> bool:
    settings = get_settings()
    value = path if isinstance(path, str) else ""
    return resolve_media_path(settings, value) is not None


templates.env.globals["media_url"] = media_url
templates.env.globals["photo_view_url"] = photo_view_url
templates.env.globals["static_url"] = static_url
templates.env.globals["STATIC_ASSET_VERSION"] = STATIC_ASSET_VERSION
templates.env.globals["media_exists"] = media_exists
templates.env.globals["has_media_path"] = has_media_path
templates.env.globals["safe_external_url"] = safe_external_url
templates.env.filters["bool_class"] = bool_class
templates.env.filters["dash"] = dash_if_empty
templates.env.filters["format_bool"] = format_bool
templates.env.filters["format_birth_year"] = format_birth_year
templates.env.filters["format_date"] = format_date
templates.env.filters["format_birth_year_input"] = format_birth_year_input
templates.env.filters["format_date_input"] = format_date_input
templates.env.filters["format_money"] = format_money
