from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import PROJECT_ROOT
from .routers import dashboard, delete_preflight, guides, health, legacy, marks, media, persons, photos, rewards, search, updates
from .version import APP_VERSION


app = FastAPI(title="Fedorinov Rewards", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "backend" / "app" / "static"), name="static")

app.include_router(dashboard.router)
app.include_router(legacy.router)
app.include_router(delete_preflight.router)
app.include_router(persons.router)
app.include_router(rewards.router)
app.include_router(marks.router)
app.include_router(guides.router)
app.include_router(search.router)
app.include_router(health.router)
app.include_router(media.router)
app.include_router(photos.router)
app.include_router(updates.router)
