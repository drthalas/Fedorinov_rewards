from fastapi.templating import Jinja2Templates

from ..config import PROJECT_ROOT


templates = Jinja2Templates(directory=PROJECT_ROOT / "backend" / "app" / "templates")
