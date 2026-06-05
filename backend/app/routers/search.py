from io import StringIO
import csv
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..repositories.search import search_all
from ..services.save_dialog import SaveDialogCancelled, SaveDialogError, choose_save_path
from .templates import templates


router = APIRouter()


async def _read_form(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _with_message(url: str, message: str) -> str:
    if not url:
        url = "/search"
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "message"]
    if message:
        query.append(("message", message))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _search_csv_text(q: str, scope: str, mode: str) -> str:
    settings = get_settings()
    results = search_all(settings.rewards_db_path, q, limit=100, scope=scope, mode=mode) if settings.db_exists and (q.strip() or scope != "all") else None
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
    return output.getvalue()


@router.get("/search")
def search_index(request: Request, q: str = "", scope: str = "all", mode: str = "contains"):
    settings = get_settings()
    results = search_all(settings.rewards_db_path, q, limit=50, scope=scope, mode=mode) if settings.db_exists else search_all(settings.rewards_db_path, "", limit=50, scope=scope, mode=mode)
    return templates.TemplateResponse(
        request,
        "search.html",
        {"settings": settings, "q": q, "scope": results["scope"], "mode": results["mode"], "results": results, "message": request.query_params.get("message", "")},
    )


@router.get("/search.csv")
def search_csv(q: str = "", scope: str = "all", mode: str = "contains"):
    filename = "search_results.csv"
    return Response(
        content=_search_csv_text(q, scope, mode),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/search.csv/save")
async def search_csv_save(request: Request):
    form_values = await _read_form(request)
    q = str(form_values.get("q") or "")
    scope = str(form_values.get("scope") or "all")
    mode = str(form_values.get("mode") or "contains")
    return_to = str(form_values.get("return_to") or "/search")
    try:
        target_path = choose_save_path(
            default_filename="search_results.csv",
            title="Сохранить CSV поиска",
            filetypes=(("CSV", "*.csv"), ("Все файлы", "*.*")),
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(_search_csv_text(q, scope, mode), encoding="utf-8")
    except SaveDialogCancelled:
        return RedirectResponse(_with_message(return_to, "Сохранение CSV отменено."), status_code=303)
    except SaveDialogError as exc:
        return RedirectResponse(_with_message(return_to, str(exc)), status_code=303)
    return RedirectResponse(_with_message(return_to, f"CSV сохранён: {target_path}"), status_code=303)
