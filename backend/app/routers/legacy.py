from pathlib import Path
import subprocess

from fastapi import APIRouter, Request, Response

from ..config import PROJECT_ROOT, get_settings
from ..repositories.common import fetch_one, table_counts
from ..repositories.marks import count_marks, get_mark, list_marks, mark_photo_items
from ..repositories.persons import count_persons, get_person, list_person_rewards, list_persons
from ..repositories.search import search_all
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
    status: str = "",
    message: str = "",
):
    settings = get_settings()
    active_tab = tab if tab in VALID_TABS else "rewards"
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
        "person_rewards": [],
        "marks": [],
        "selected_mark": None,
        "selected_mark_photos": [],
        "q": q,
        "scope": scope,
        "mode": mode,
        "search_results": None,
        "summary": None,
        "commit": _current_commit(),
    }

    if not settings.db_exists:
        return templates.TemplateResponse(request, "legacy.html", context)

    persons_total = count_persons(settings.rewards_db_path)
    persons = list_persons(settings.rewards_db_path, limit=max(persons_total, 1), offset=0)
    context["persons"] = persons
    context["persons_total"] = persons_total

    marks_total = count_marks(settings.rewards_db_path)
    marks = list_marks(settings.rewards_db_path, limit=max(marks_total, 1), offset=0)
    context["marks"] = marks
    context["marks_total"] = marks_total

    selected_person_id = person_id or (int(persons[0]["id"]) if persons else None)
    if selected_person_id is not None:
        selected_person = get_person(settings.rewards_db_path, selected_person_id)
        context["selected_person"] = selected_person
        context["person_rewards"] = list_person_rewards(settings.rewards_db_path, selected_person_id)

    selected_mark_id = mark_id or (int(marks[0]["id"]) if marks else None)
    if selected_mark_id is not None:
        selected_mark = get_mark(settings.rewards_db_path, selected_mark_id)
        context["selected_mark"] = selected_mark
        context["selected_mark_photos"] = mark_photo_items(selected_mark) if selected_mark else []

    if active_tab == "search" and q.strip():
        search_results = search_all(settings.rewards_db_path, q, limit=25, scope=scope, mode=mode)
        context["search_results"] = search_results
        context["scope"] = search_results["scope"]
        context["mode"] = search_results["mode"]

    if active_tab == "summary":
        context["summary"] = _legacy_summary(settings.rewards_db_path)

    return templates.TemplateResponse(request, "legacy.html", context)


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
