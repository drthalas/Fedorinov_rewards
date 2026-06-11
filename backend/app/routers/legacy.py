from pathlib import Path
import subprocess
from urllib.parse import parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from starlette.datastructures import URL

from ..config import PROJECT_ROOT, get_settings
from ..repositories.common import fetch_one, table_counts
from ..repositories.legacy_rewards import (
    legacy_rewards_filter_cascade,
    legacy_rewards_filter_options,
    legacy_rewards_totals,
    list_legacy_reward_persons,
    normalized_legacy_rewards_filters,
)
from ..repositories.marks import count_marks, get_mark, list_marks, mark_photo_items
from ..repositories.persons import get_person, list_person_rewards
from ..repositories.search import search_all, search_suggestions
from ..repositories.summary import (
    summary_filter_cascade,
    summary_filter_options,
    normalized_summary_filters,
    summary_matrix,
    summary_matrix_csv_text,
    summary_csv_text,
    summary_rows,
    summary_totals,
)
from ..services.update_checker import check_for_updates
from ..services.save_dialog import SaveDialogCancelled, SaveDialogError, choose_save_path
from ..services.person_files import person_archive_filename
from ..services.summary_pdf import SummaryPDFError, SummaryPDFTooWide, generate_summary_matrix_pdf, generate_summary_pdf
from ..version import APP_NAME, APP_VERSION
from .templates import templates


router = APIRouter()

VALID_TABS = {"rewards", "search", "marks", "summary", "about"}
STATUS_MESSAGES = {
    "created": "Награждённый добавлен.",
    "updated": "Изменения сохранены.",
    "deleted": "Запись удалена.",
    "delete_blocked": "Нельзя удалить: у награждённого есть награды.",
    "reward_created": "Награда добавлена.",
    "reward_deleted": "Награда удалена.",
    "mark_created": "Знак добавлен.",
    "mark_deleted": "Знак удалён.",
}


def _summary_query_params(filters) -> dict[str, object]:
    params: dict[str, object] = {}
    if filters.country_id is not None:
        params["country_id"] = filters.country_id
    if filters.category_id is not None:
        params["category_id"] = filters.category_id
    if filters.subcategory_id is not None:
        params["subcategory_id"] = filters.subcategory_id
    if filters.name_id is not None:
        params["name_id"] = filters.name_id
    if filters.extra:
        params["extra"] = filters.extra
    if filters.include_marks:
        params["include_marks"] = "true"
    return params


def _summary_url(filters, summary_mode: str) -> str:
    params = {"tab": "summary", "summary_mode": summary_mode}
    params.update(_summary_query_params(filters))
    return str(URL(path="/legacy").include_query_params(**params))


def _normalized_matrix_sort(sort_by: str = "", sort_dir: str = "") -> tuple[str, str]:
    clean_sort = str(sort_by or "fio").strip()
    if not clean_sort:
        clean_sort = "fio"
    clean_dir = "desc" if str(sort_dir or "").strip().lower() == "desc" else "asc"
    return clean_sort, clean_dir


def _summary_sort_url(filters, sort_key: str, current_sort: str, current_dir: str) -> str:
    next_dir = "desc" if sort_key == current_sort and current_dir == "asc" else "asc"
    params = {
        "tab": "summary",
        "summary_mode": "matrix",
        "matrix_sort": sort_key,
        "matrix_dir": next_dir,
    }
    params.update(_summary_query_params(filters))
    return str(URL(path="/legacy").include_query_params(**params))


def _matrix_sort_context(matrix: dict[str, object], filters, current_sort: str, current_dir: str) -> dict[str, object]:
    sort_urls = {
        "fio": _summary_sort_url(filters, "fio", current_sort, current_dir),
        "rank_name": _summary_sort_url(filters, "rank_name", current_sort, current_dir),
        "birthday": _summary_sort_url(filters, "birthday", current_sort, current_dir),
        "numbers": _summary_sort_url(filters, "numbers", current_sort, current_dir),
        "row_total": _summary_sort_url(filters, "row_total", current_sort, current_dir),
    }
    photo_sort_urls = {
        str(column["field"]): _summary_sort_url(filters, f"photo:{column['field']}", current_sort, current_dir)
        for column in matrix.get("photo_columns") or []
    }
    reward_sort_urls = {
        str(column["id"]): _summary_sort_url(filters, f"reward:{column['id']}", current_sort, current_dir)
        for column in matrix.get("reward_columns") or []
    }
    return {
        "sort": current_sort,
        "dir": current_dir,
        "urls": sort_urls,
        "photo_urls": photo_sort_urls,
        "reward_urls": reward_sort_urls,
    }


async def _read_form(request: Request) -> dict[str, object]:
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _with_message(url: str, message: str) -> str:
    if not url:
        url = "/legacy?tab=summary"
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query = [(key, value) for key, value in query if key != "message"]
    if message:
        query.append(("message", message))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _write_csv_to_chosen_path(default_filename: str, title: str, content: str) -> Path:
    target_path = choose_save_path(
        default_filename=default_filename,
        title=title,
        filetypes=(("CSV", "*.csv"), ("Все файлы", "*.*")),
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return target_path


def _rewards_query_params(filters, person_id: int | None = None) -> dict[str, object]:
    params: dict[str, object] = {"tab": "rewards"}
    if person_id is not None:
        params["person_id"] = person_id
    if filters.rank_id is not None:
        params["rank_id"] = filters.rank_id
    if filters.country_id is not None:
        params["country_id"] = filters.country_id
    if filters.category_id is not None:
        params["category_id"] = filters.category_id
    if filters.subcategory_id is not None:
        params["subcategory_id"] = filters.subcategory_id
    if filters.name_id is not None:
        params["name_id"] = filters.name_id
    return params


def _legacy_rewards_url(filters, person_id: int | None = None) -> str:
    return str(URL(path="/legacy").include_query_params(**_rewards_query_params(filters, person_id)))


def _legacy_search_url(q: str, scope: str, mode: str, sort: str = "", direction: str = "asc") -> str:
    params = {"tab": "search", "q": q, "scope": scope, "mode": mode}
    if sort:
        params["sort"] = sort
        params["dir"] = "desc" if direction == "desc" else "asc"
    return str(URL(path="/legacy").include_query_params(**params))


def _search_sort_context(path: str, q: str, scope: str, mode: str, current_sort: str, current_dir: str, extra: dict[str, str] | None = None) -> dict[str, object]:
    def url_for(sort_key: str) -> str:
        next_dir = "desc" if current_sort == sort_key and current_dir == "asc" else "asc"
        if path == "/legacy":
            return _legacy_search_url(q, scope, mode, sort_key, next_dir)
        params = {"q": q, "scope": scope, "mode": mode, "sort": sort_key, "dir": next_dir}
        if extra:
            params.update(extra)
        return str(URL(path=path).include_query_params(**params))

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


def _current_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _sum_row(db_path: Path, table: str) -> dict[str, object]:
    return fetch_one(
        db_path,
        f"""
        select
            count(*) as total,
            coalesce(sum(cast(price_purchase as integer)), 0) as price_purchase_sum,
            coalesce(sum(cast(price_now as integer)), 0) as price_now_sum,
            sum(case when lower(cast(instock as text)) = 'true' then 1 else 0 end) as in_stock,
            sum(case when lower(cast(instock as text)) = 'false' then 1 else 0 end) as not_in_stock
        from {table}
        """,
    ) or {"total": 0, "price_purchase_sum": 0, "price_now_sum": 0, "in_stock": 0, "not_in_stock": 0}


def _legacy_summary(db_path: Path) -> dict[str, object]:
    counts = table_counts(db_path, ["person", "rewards", "mark"])
    return {
        "counts": counts,
        "rewards": _sum_row(db_path, "rewards"),
        "marks": _sum_row(db_path, "mark"),
    }


@router.get("/legacy")
def legacy_index(
    request: Request,
    tab: str = "rewards",
    person_id: int | None = None,
    mark_id: int | None = None,
    q: str = "",
    scope: str = "all",
    mode: str = "contains",
    sort: str = "",
    dir: str = "asc",
    status: str = "",
    message: str = "",
    rank_id: str | None = None,
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
    summary_mode: str = "matrix",
    matrix_sort: str = "fio",
    matrix_dir: str = "asc",
    check_updates: str | None = None,
):
    settings = get_settings()
    active_tab = tab if tab in VALID_TABS else "rewards"
    active_summary_mode = "aggregate" if summary_mode == "aggregate" else "matrix"
    active_matrix_sort, active_matrix_dir = _normalized_matrix_sort(matrix_sort, matrix_dir)
    rewards_filters = normalized_legacy_rewards_filters(
        rank_id=rank_id,
        country_id=country_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        name_id=name_id,
    )
    context: dict[str, object] = {
        "settings": settings,
        "tab": active_tab,
        "tabs": [
            ("rewards", "Награды"),
            ("search", "Поиск"),
            ("marks", "Знаки"),
            ("summary", "Свод.таблица"),
            ("about", "О программе"),
        ],
        "message": message,
        "status_message": STATUS_MESSAGES.get(status),
        "persons": [],
        "selected_person": None,
        "selected_person_archive_filename": "",
        "person_rewards": [],
        "persons_total": 0,
        "rewards_filters": rewards_filters,
        "rewards_filter_options": {"ranks": [], "countries": [], "categories": [], "subcategories": [], "names": []},
        "rewards_filter_cascade": {},
        "rewards_filter_active": any(
            value is not None
            for value in (
                rewards_filters.rank_id,
                rewards_filters.country_id,
                rewards_filters.category_id,
                rewards_filters.subcategory_id,
                rewards_filters.name_id,
            )
        ),
        "rewards_tab_return": _legacy_rewards_url(rewards_filters),
        "selected_person_return": _legacy_rewards_url(rewards_filters, person_id) if person_id is not None else _legacy_rewards_url(rewards_filters),
        "rewards_totals": {
            "persons_total": 0,
            "rewards_total": 0,
            "in_stock": 0,
            "not_in_stock": 0,
            "price_purchase_sum": 0,
            "price_now_sum": 0,
            "last_purchase_date": None,
        },
        "marks": [],
        "selected_mark": None,
        "selected_mark_photos": [],
        "q": q,
        "scope": scope,
        "mode": mode,
        "sort": sort,
        "dir": "desc" if str(dir or "").strip().lower() == "desc" else "asc",
        "search_results": None,
        "search_suggestions": {},
        "search_return_to": _legacy_search_url(q, scope, mode, sort, dir),
        "search_sort": _search_sort_context("/legacy", q, scope, mode, sort, "desc" if str(dir or "").strip().lower() == "desc" else "asc"),
        "summary": None,
        "summary_filters": normalized_summary_filters(
            country_id=country_id,
            category_id=category_id,
            subcategory_id=subcategory_id,
            name_id=name_id,
            extra=extra,
            include_marks=include_marks,
        ),
        "summary_options": {"countries": [], "categories": [], "subcategories": [], "names": [], "extras": []},
        "summary_filter_cascade": {},
        "summary_rows": [],
        "summary_totals": {"total": 0, "in_stock": 0, "not_in_stock": 0, "price_purchase_sum": 0, "price_now_sum": 0},
        "summary_mode": active_summary_mode,
        "matrix_sort": active_matrix_sort,
        "matrix_dir": active_matrix_dir,
        "summary_matrix_sort": {"sort": active_matrix_sort, "dir": active_matrix_dir, "urls": {}, "photo_urls": {}, "reward_urls": {}},
        "summary_csv_url": "/summary.csv",
        "summary_matrix": None,
        "summary_matrix_csv_url": "/summary_matrix.csv",
        "summary_matrix_mode_url": "/legacy?tab=summary&summary_mode=matrix",
        "summary_aggregate_mode_url": "/legacy?tab=summary&summary_mode=aggregate",
        "commit": _current_commit(),
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "check_updates": str(check_updates or "").strip().lower() in {"1", "true", "yes", "on"},
        "update_check": None,
    }

    if not settings.db_exists:
        return templates.TemplateResponse(request, "legacy.html", context)

    context["rewards_filter_options"] = legacy_rewards_filter_options(settings.rewards_db_path, rewards_filters)
    context["rewards_filter_cascade"] = legacy_rewards_filter_cascade(settings.rewards_db_path)
    persons = list_legacy_reward_persons(settings.rewards_db_path, rewards_filters)
    for person in persons:
        row_id = int(person["id"])
        person["legacy_url"] = _legacy_rewards_url(rewards_filters, row_id)
        person["detail_url"] = str(URL(path=f"/persons/{row_id}").include_query_params(return_to=person["legacy_url"]))
    context["persons"] = persons
    context["persons_total"] = len(persons)
    context["rewards_totals"] = legacy_rewards_totals(settings.rewards_db_path, rewards_filters)

    marks_total = count_marks(settings.rewards_db_path)
    marks = list_marks(settings.rewards_db_path, limit=max(marks_total, 1), offset=0)
    context["marks"] = marks
    context["marks_total"] = marks_total

    person_ids = {int(row["id"]) for row in persons}
    selected_person_id = person_id if person_id in person_ids else (int(persons[0]["id"]) if persons else None)
    if selected_person_id is not None:
        selected_person = get_person(settings.rewards_db_path, selected_person_id)
        context["selected_person"] = selected_person
        context["person_rewards"] = list_person_rewards(settings.rewards_db_path, selected_person_id)
        context["selected_person_return"] = _legacy_rewards_url(rewards_filters, selected_person_id)
        if selected_person is not None:
            context["selected_person_archive_filename"] = person_archive_filename(str(selected_person.get("fio") or "person"), selected_person_id)

    selected_mark_id = mark_id or (int(marks[0]["id"]) if marks else None)
    if selected_mark_id is not None:
        selected_mark = get_mark(settings.rewards_db_path, selected_mark_id)
        context["selected_mark"] = selected_mark
        context["selected_mark_photos"] = mark_photo_items(selected_mark) if selected_mark else []

    if active_tab == "search" and (q.strip() or scope != "all"):
        search_results = search_all(settings.rewards_db_path, q, limit=50, scope=scope, mode=mode, sort_by=sort, sort_dir=dir)
        context["search_results"] = search_results
        context["scope"] = search_results["scope"]
        context["mode"] = search_results["mode"]
        context["sort"] = search_results["sort_by"]
        context["dir"] = search_results["sort_dir"]
        context["search_return_to"] = _legacy_search_url(q, search_results["scope"], search_results["mode"], search_results["sort_by"], search_results["sort_dir"])
        context["search_sort"] = _search_sort_context(
            "/legacy",
            q,
            search_results["scope"],
            search_results["mode"],
            search_results["sort_by"],
            search_results["sort_dir"],
        )
    if active_tab == "search":
        context["search_suggestions"] = search_suggestions(settings.rewards_db_path)

    if active_tab == "summary":
        context["summary"] = _legacy_summary(settings.rewards_db_path)
        context["summary_options"] = summary_filter_options(settings.rewards_db_path, context["summary_filters"])
        context["summary_filter_cascade"] = summary_filter_cascade(settings.rewards_db_path)
        rows = summary_rows(settings.rewards_db_path, context["summary_filters"])
        context["summary_rows"] = rows
        context["summary_totals"] = summary_totals(rows)
        context["summary_csv_url"] = str(URL(path="/summary.csv").include_query_params(**_summary_query_params(context["summary_filters"])))
        context["summary_matrix"] = summary_matrix(settings.rewards_db_path, context["summary_filters"], active_matrix_sort, active_matrix_dir)
        context["summary_matrix_csv_url"] = str(
            URL(path="/summary_matrix.csv").include_query_params(**_summary_query_params(context["summary_filters"]))
        )
        context["summary_matrix_sort"] = _matrix_sort_context(
            context["summary_matrix"],
            context["summary_filters"],
            active_matrix_sort,
            active_matrix_dir,
        )
        context["summary_matrix_mode_url"] = _summary_url(context["summary_filters"], "matrix")
        context["summary_aggregate_mode_url"] = _summary_url(context["summary_filters"], "aggregate")

    if active_tab == "about" and context["check_updates"]:
        context["update_check"] = check_for_updates(settings)

    return templates.TemplateResponse(request, "legacy.html", context)


@router.get("/summary.csv")
def summary_csv(
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
):
    settings = get_settings()
    rows = []
    if settings.db_exists:
        filters = normalized_summary_filters(
            country_id=country_id,
            category_id=category_id,
            subcategory_id=subcategory_id,
            name_id=name_id,
            extra=extra,
            include_marks=include_marks,
        )
        rows = summary_rows(settings.rewards_db_path, filters)
    return Response(
        content=summary_csv_text(rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="summary.csv"'},
    )


@router.post("/summary.csv/save")
async def summary_csv_save(request: Request):
    form_values = await _read_form(request)
    return_to = str(form_values.get("return_to") or "/legacy?tab=summary&summary_mode=aggregate")
    filters = normalized_summary_filters(
        country_id=str(form_values.get("country_id") or ""),
        category_id=str(form_values.get("category_id") or ""),
        subcategory_id=str(form_values.get("subcategory_id") or ""),
        name_id=str(form_values.get("name_id") or ""),
        extra=str(form_values.get("extra") or ""),
        include_marks=str(form_values.get("include_marks") or ""),
    )
    settings = get_settings()
    rows = summary_rows(settings.rewards_db_path, filters) if settings.db_exists else []
    try:
        path = _write_csv_to_chosen_path("summary.csv", "Сохранить CSV сводной таблицы", summary_csv_text(rows))
    except SaveDialogCancelled:
        return RedirectResponse(_with_message(return_to, "Сохранение CSV отменено."), status_code=303)
    except SaveDialogError as exc:
        return RedirectResponse(_with_message(return_to, str(exc)), status_code=303)
    return RedirectResponse(_with_message(return_to, f"CSV сохранён: {path}"), status_code=303)


@router.head("/summary.csv")
def summary_csv_head(
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
):
    normalized_summary_filters(
        country_id=country_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        name_id=name_id,
        extra=extra,
        include_marks=include_marks,
    )
    return Response(
        status_code=200,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="summary.csv"'},
    )


@router.get("/summary.pdf")
def summary_pdf(
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
):
    settings = get_settings()
    filters = normalized_summary_filters(
        country_id=country_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        name_id=name_id,
        extra=extra,
        include_marks=include_marks,
    )
    if not settings.db_exists:
        return Response(content=b"", media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="summary.pdf"'})
    try:
        result = generate_summary_pdf(settings.rewards_db_path, filters)
    except SummaryPDFError as exc:
        return Response(content=str(exc), status_code=500, media_type="text/plain; charset=utf-8")
    return Response(
        content=result.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.head("/summary.pdf")
def summary_pdf_head(
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
):
    normalized_summary_filters(
        country_id=country_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        name_id=name_id,
        extra=extra,
        include_marks=include_marks,
    )
    return Response(status_code=200, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="summary.pdf"'})


@router.get("/summary_matrix.csv")
def summary_matrix_csv(
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
):
    settings = get_settings()
    matrix = {"photo_columns": [], "reward_columns": [], "rows": [], "photo_totals": {}, "reward_totals": {}, "person_total": 0, "reward_total": 0}
    if settings.db_exists:
        filters = normalized_summary_filters(
            country_id=country_id,
            category_id=category_id,
            subcategory_id=subcategory_id,
            name_id=name_id,
            extra=extra,
            include_marks=include_marks,
        )
        matrix = summary_matrix(settings.rewards_db_path, filters)
    return Response(
        content=summary_matrix_csv_text(matrix),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="summary_matrix.csv"'},
    )


@router.get("/summary_matrix.pdf")
def summary_matrix_pdf(
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
):
    settings = get_settings()
    filters = normalized_summary_filters(
        country_id=country_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        name_id=name_id,
        extra=extra,
        include_marks=include_marks,
    )
    if not settings.db_exists:
        return Response(content=b"", media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="summary_matrix.pdf"'})
    try:
        result = generate_summary_matrix_pdf(settings.rewards_db_path, filters)
    except SummaryPDFTooWide as exc:
        return Response(content=str(exc), status_code=400, media_type="text/plain; charset=utf-8")
    except SummaryPDFError as exc:
        return Response(content=str(exc), status_code=500, media_type="text/plain; charset=utf-8")
    return Response(
        content=result.content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.head("/summary_matrix.pdf")
def summary_matrix_pdf_head(
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
):
    normalized_summary_filters(
        country_id=country_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        name_id=name_id,
        extra=extra,
        include_marks=include_marks,
    )
    return Response(
        status_code=200,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="summary_matrix.pdf"'},
    )


@router.post("/summary_matrix.csv/save")
async def summary_matrix_csv_save(request: Request):
    form_values = await _read_form(request)
    return_to = str(form_values.get("return_to") or "/legacy?tab=summary&summary_mode=matrix")
    filters = normalized_summary_filters(
        country_id=str(form_values.get("country_id") or ""),
        category_id=str(form_values.get("category_id") or ""),
        subcategory_id=str(form_values.get("subcategory_id") or ""),
        name_id=str(form_values.get("name_id") or ""),
        extra=str(form_values.get("extra") or ""),
        include_marks=str(form_values.get("include_marks") or ""),
    )
    settings = get_settings()
    matrix = (
        summary_matrix(settings.rewards_db_path, filters)
        if settings.db_exists
        else {"photo_columns": [], "reward_columns": [], "rows": [], "photo_totals": {}, "reward_totals": {}, "person_total": 0, "reward_total": 0}
    )
    try:
        path = _write_csv_to_chosen_path("summary_matrix.csv", "Сохранить CSV шахматки", summary_matrix_csv_text(matrix))
    except SaveDialogCancelled:
        return RedirectResponse(_with_message(return_to, "Сохранение CSV отменено."), status_code=303)
    except SaveDialogError as exc:
        return RedirectResponse(_with_message(return_to, str(exc)), status_code=303)
    return RedirectResponse(_with_message(return_to, f"CSV сохранён: {path}"), status_code=303)


@router.head("/summary_matrix.csv")
def summary_matrix_csv_head(
    country_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    name_id: str | None = None,
    extra: str = "",
    include_marks: str | None = None,
):
    normalized_summary_filters(
        country_id=country_id,
        category_id=category_id,
        subcategory_id=subcategory_id,
        name_id=name_id,
        extra=extra,
        include_marks=include_marks,
    )
    return Response(
        status_code=200,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="summary_matrix.csv"'},
    )


@router.head("/legacy")
def legacy_head(
    tab: str = "rewards",
    person_id: int | None = None,
    mark_id: int | None = None,
    q: str = "",
    scope: str = "all",
    mode: str = "contains",
    message: str = "",
):
    return Response(status_code=200)
