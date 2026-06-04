from io import StringIO
import csv

from fastapi import APIRouter, Request, Response

from ..config import get_settings
from ..repositories.search import search_all
from .templates import templates


router = APIRouter()


@router.get("/search")
def search_index(request: Request, q: str = "", scope: str = "all", mode: str = "contains"):
    settings = get_settings()
    results = search_all(settings.rewards_db_path, "", limit=25, scope=scope, mode=mode)
    if q.strip() and settings.db_exists:
        results = search_all(settings.rewards_db_path, q, limit=25, scope=scope, mode=mode)
    return templates.TemplateResponse(
        request,
        "search.html",
        {"settings": settings, "q": q, "scope": results["scope"], "mode": results["mode"], "results": results},
    )


@router.get("/search.csv")
def search_csv(q: str = "", scope: str = "all", mode: str = "contains"):
    settings = get_settings()
    results = search_all(settings.rewards_db_path, q, limit=100, scope=scope, mode=mode) if q.strip() else None
    output = StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["group", "id", "title", "number", "owner", "status"])
    if results:
        for person in results["persons"]:
            writer.writerow(["persons", person.get("id"), person.get("fio"), "", "", person.get("rank_name")])
        for reward in results["rewards"]:
            writer.writerow(["rewards", reward.get("id"), reward.get("name"), reward.get("number"), reward.get("fio"), reward.get("instock")])
        for mark in results["marks"]:
            writer.writerow(["marks", mark.get("id"), mark.get("name"), mark.get("number"), "", mark.get("instock")])
    filename = "search_results.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
