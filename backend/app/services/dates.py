from datetime import date, datetime
import re


DATE_INPUT_MESSAGE = "Укажите дату в формате ДД.ММ.ГГГГ."
BIRTH_YEAR_INPUT_MESSAGE = "Укажите год рождения в формате ГГГГ."
BIRTH_YEAR_REQUIRED_MESSAGE = "Укажите год рождения."
BIRTH_YEAR_RANGE_MESSAGE = "Год рождения должен быть от {minimum_year} до {maximum_year}."
BIRTH_YEAR_MINIMUM = 1800
BIRTH_YEAR_MAXIMUM = 1999


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


def format_birth_year_input(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{4}", text):
        return text
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], pattern).strftime("%Y")
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


def normalize_birth_year_input(
    value: object,
    *,
    required: bool = False,
    minimum_year: int = BIRTH_YEAR_MINIMUM,
    maximum_year: int = BIRTH_YEAR_MAXIMUM,
) -> str | None:
    text = "" if value is None else str(value).strip()
    if not text:
        if required:
            raise ValueError(BIRTH_YEAR_REQUIRED_MESSAGE)
        return None
    if not re.fullmatch(r"[0-9]{4}", text):
        raise ValueError(BIRTH_YEAR_INPUT_MESSAGE)
    year = int(text)
    if year < minimum_year or year > maximum_year:
        raise ValueError(
            BIRTH_YEAR_RANGE_MESSAGE.format(
                minimum_year=minimum_year,
                maximum_year=maximum_year,
            )
        )
    return text
