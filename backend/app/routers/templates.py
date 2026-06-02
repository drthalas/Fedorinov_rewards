from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

from ..config import PROJECT_ROOT
from ..services.display import bool_class, dash_if_empty, format_bool, format_date, format_money, has_media_path


templates = Jinja2Templates(directory=PROJECT_ROOT / "backend" / "app" / "templates")


def media_url(path: object) -> str:
    value = path if isinstance(path, str) else ""
    return str(URL(path="/media").include_query_params(path=value))


templates.env.globals["media_url"] = media_url
templates.env.globals["has_media_path"] = has_media_path
templates.env.filters["bool_class"] = bool_class
templates.env.filters["dash"] = dash_if_empty
templates.env.filters["format_bool"] = format_bool
templates.env.filters["format_date"] = format_date
templates.env.filters["format_money"] = format_money
