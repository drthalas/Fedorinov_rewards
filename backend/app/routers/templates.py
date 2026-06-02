from fastapi.templating import Jinja2Templates
from starlette.datastructures import URL

from ..config import PROJECT_ROOT


templates = Jinja2Templates(directory=PROJECT_ROOT / "backend" / "app" / "templates")


def media_url(path: object) -> str:
    value = path if isinstance(path, str) else ""
    return str(URL(path="/media").include_query_params(path=value))


templates.env.globals["media_url"] = media_url
