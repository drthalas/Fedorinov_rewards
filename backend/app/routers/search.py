from io import StringIO
import csv
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from ..config import get_settings
from ..repositories.search import search_all, search_suggestions
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


def _search_csv_text(q: str, scope: str, mode: str, sort: str = "", direction: str = "asc", db_path: Path | None = None) -> str:
    settings = get_settings()
    active_db_path = db_path or settings.rewards_db_path
    db_available = db_path is not None or settings.db_exists
    results = (
        search_all(active_db_path, q, limit=100, scope=scope, mode=mode, sort_by=sort, sort_dir=direction)
        if db_available and (q.strip() or scope != "all")
        else None
    )
    output = StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Группа",
        "ID",
        "ФИО",
        "Звание / специальность",
        "Дата рождения",
        "Наименование",
        "Номер",
        "Дата покупки",
        "Цена покупки",
        "Текущая цена",
        "Наличие",
        "Фото наградной книжки, сторона 1",
        "Фото наградной книжки, сторона 2",
        "Фото учётной карточки, страница 1",
        "Фото учётной карточки, страница 2",
        "Фото награды: аверс",
        "Фото награды: реверс",
        "Наградной лист",
    ])
    if results:
        for person in results["persons"]:
            writer.writerow([
                "Награждённые",
                person.get("id"),
                person.get("fio"),
                person.get("rank_name"),
                person.get("birthday"),
                "",
                "",
                "",
                "",
                "",
                "",
                person.get("book1_foto_flag"),
                person.get("book2_foto_flag"),
                person.get("card1_foto_flag"),
                person.get("card2_foto_flag"),
                "",
                "",
                "",
            ])
        for reward in results["rewards"]:
            writer.writerow([
                "Награды",
                reward.get("id"),
                reward.get("fio"),
                reward.get("rank_name"),
                reward.get("birthday"),
                reward.get("name"),
                reward.get("number"),
                reward.get("date_purchase"),
                reward.get("price_purchase"),
                reward.get("price_now"),
                reward.get("instock"),
                reward.get("person_book1_foto_flag"),
                reward.get("person_book2_foto_flag"),
                reward.get("person_card1_foto_flag"),
                reward.get("person_card2_foto_flag"),
                reward.get("front_foto_flag"),
                reward.get("back_foto_flag"),
                reward.get("reward_list_flag"),
            ])
        for mark in results["marks"]:
            writer.writerow(["Знаки", mark.get("id"), "", "", "", mark.get("name"), mark.get("number"), "", "", "", mark.get("instock"), "", "", "", "", "", "", ""])
    return output.getvalue()


def _search_url(path: str, q: str, scope: str, mode: str, sort: str = "", direction: str = "asc", extra: dict[str, str] | None = None) -> str:
    params = {"q": q, "scope": scope, "mode": mode}
    if sort:
        params["sort"] = sort
        params["dir"] = "desc" if direction == "desc" else "asc"
    if extra:
        params.update(extra)
    return urlunsplit(("", "", path, urlencode(params), ""))


def _search_sort_context(path: str, q: str, scope: str, mode: str, current_sort: str, current_dir: str, extra: dict[str, str] | None = None) -> dict[str, object]:
    def url_for(sort_key: str) -> str:
        next_dir = "desc" if current_sort == sort_key and current_dir == "asc" else "asc"
        return _search_url(path, q, scope, mode, sort_key, next_dir, extra)

    keys = [
        "fio",
        "rank_name",
        "birthday",
        "name",
        "number",
        "date_purchase",
        "price_purchase",
        "price_now",
        "instock",
        "person_foto_flag",
        "main_foto_flag",
        "rewards_foto_flag",
        "book1_foto_flag",
        "book2_foto_flag",
        "card1_foto_flag",
        "card2_foto_flag",
        "person_book1_foto_flag",
        "person_book2_foto_flag",
        "person_card1_foto_flag",
        "person_card2_foto_flag",
        "front_foto_flag",
        "back_foto_flag",
        "reward_list_flag",
    ]
    return {
        "sort": current_sort,
        "dir": current_dir,
        "urls": {key: url_for(key) for key in keys},
    }


@router.get("/search")
def search_index(request: Request, q: str = "", scope: str = "all", mode: str = "contains", sort: str = "", dir: str = "asc"):
    settings = get_settings()
    results = (
        search_all(settings.rewards_db_path, q, limit=50, scope=scope, mode=mode, sort_by=sort, sort_dir=dir)
        if settings.db_exists
        else search_all(settings.rewards_db_path, "", limit=50, scope=scope, mode=mode, sort_by=sort, sort_dir=dir)
    )
    return_to = _search_url("/search", q, results["scope"], results["mode"], results["sort_by"], results["sort_dir"])
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "settings": settings,
            "q": q,
            "scope": results["scope"],
            "mode": results["mode"],
            "sort": results["sort_by"],
            "dir": results["sort_dir"],
            "results": results,
            "message": request.query_params.get("message", ""),
            "search_suggestions": search_suggestions(settings.rewards_db_path) if settings.db_exists else {},
            "search_return_to": return_to,
            "search_sort": _search_sort_context("/search", q, results["scope"], results["mode"], results["sort_by"], results["sort_dir"]),
        },
    )


@router.get("/search.csv")
def search_csv(q: str = "", scope: str = "all", mode: str = "contains", sort: str = "", dir: str = "asc"):
    filename = "search_results.csv"
    return Response(
        content=_search_csv_text(q, scope, mode, sort, dir),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/search.csv/save")
async def search_csv_save(request: Request):
    form_values = await _read_form(request)
    q = str(form_values.get("q") or "")
    scope = str(form_values.get("scope") or "all")
    mode = str(form_values.get("mode") or "contains")
    sort = str(form_values.get("sort") or "")
    direction = str(form_values.get("dir") or "asc")
    return_to = str(form_values.get("return_to") or "/search")
    try:
        target_path = choose_save_path(
            default_filename="search_results.csv",
            title="Сохранить CSV поиска",
            filetypes=(("CSV", "*.csv"), ("Все файлы", "*.*")),
        )
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(_search_csv_text(q, scope, mode, sort, direction), encoding="utf-8")
    except SaveDialogCancelled:
        return RedirectResponse(_with_message(return_to, "Сохранение CSV отменено."), status_code=303)
    except SaveDialogError as exc:
        return RedirectResponse(_with_message(return_to, str(exc)), status_code=303)
    return RedirectResponse(_with_message(return_to, f"CSV сохранён: {target_path}"), status_code=303)
