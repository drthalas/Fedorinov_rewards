from datetime import date, datetime


DATE_INPUT_MESSAGE = "Укажите дату в формате ДД.ММ.ГГГГ."


def today_iso() -> str:
    return date.today().isoformat()


def format_date_input(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return text


def normalize_date_input(value: object, *, required: bool = False, required_message: str = DATE_INPUT_MESSAGE) -> str | None:
    text = "" if value is None else str(value).strip()
    if not text:
        if required:
            raise ValueError(required_message)
        return None
    for pattern in ("%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(DATE_INPUT_MESSAGE)
