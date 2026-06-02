from datetime import date, datetime
from decimal import Decimal, InvalidOperation


DASH = "—"


def dash_if_empty(value: object) -> object:
    if value is None:
        return DASH
    if isinstance(value, str) and not value.strip():
        return DASH
    return value


def format_date(value: object) -> str:
    if value is None:
        return DASH
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    if not isinstance(value, str):
        return DASH

    text = value.strip()
    if not text:
        return DASH

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return DASH


def format_money(value: object) -> str:
    if value is None:
        return DASH
    if isinstance(value, str):
        value = value.strip().replace(" ", "").replace(",", ".")
        if not value:
            return DASH
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return DASH

    rounded = int(amount.quantize(Decimal("1")))
    return f"{rounded:,}".replace(",", " ") + " ₽"


def format_bool(value: object, true_label: str = "Да", false_label: str = "Нет") -> str:
    if value is None:
        return DASH
    if isinstance(value, bool):
        return true_label if value else false_label
    if isinstance(value, (int, float)):
        return true_label if value else false_label
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return DASH
        if normalized in {"true", "1", "yes", "y", "да", "в наличии"}:
            return true_label
        if normalized in {"false", "0", "no", "n", "нет"}:
            return false_label
    return DASH


def bool_class(value: object) -> str:
    label = format_bool(value)
    if label == "Да":
        return "yes"
    if label == "Нет":
        return "no"
    return "empty"


def has_media_path(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def clamp_page(value: int, minimum: int = 1) -> int:
    return max(value, minimum)


def clamp_page_size(value: int, default: int = 25, minimum: int = 1, maximum: int = 100) -> int:
    if value < minimum:
        return default
    return min(value, maximum)


def pagination(total: int, page: int, page_size: int) -> dict[str, int | bool]:
    current_page = clamp_page(page)
    current_size = clamp_page_size(page_size)
    total_pages = max((total + current_size - 1) // current_size, 1)
    if current_page > total_pages:
        current_page = total_pages
    offset = (current_page - 1) * current_size
    return {
        "page": current_page,
        "page_size": current_size,
        "total": total,
        "total_pages": total_pages,
        "offset": offset,
        "has_previous": current_page > 1,
        "has_next": current_page < total_pages,
        "previous_page": max(current_page - 1, 1),
        "next_page": min(current_page + 1, total_pages),
    }
