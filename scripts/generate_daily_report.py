#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_TITLE = "Награды и награждённые"

BANNED_TERMS = [
    "веб-версия базы",
    "база Федоринова",
    "Fedorinov_rewards",
    "legacy UI",
    "CRUD",
    "Add",
    "Fix",
    "Improve",
    "Update",
    "Release",
    "workflow",
    "backend",
    "endpoint",
    "route",
    "router",
    "repository",
    "commit",
    "hash",
    "pull",
    "push",
    "SQLite",
]

CHANGE_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "Add daily Telegram progress reports",
        ["настроили ежедневный утренний отчёт в Telegram;"],
    ),
    (
        "Add person booklet PDF",
        ["добавили PDF-буклет по кавалеру;"],
    ),
    (
        "Fix cascading guide dropdowns",
        [
            "исправили выпадающие справочники: теперь страна, категория, подкатегория и наименование корректно сужают друг друга;",
        ],
    ),
    (
        "Improve search results and suggestions",
        [
            "улучшили поиск: добавили нужные колонки, подсказки из базы и возврат к результатам;",
        ],
    ),
    (
        "Implement browser Save As for exports",
        ["добавили сохранение файлов через системное окно браузера;"],
    ),
    (
        "Polish forms validation and errors",
        ["улучшили проверки форм и русские сообщения об ошибках;"],
    ),
    (
        "Fix delete backup guard in working write mode",
        [
            "исправили удаление записей в рабочем режиме: подтверждение осталось, но лишнее требование резервной копии убрано;",
        ],
    ),
    (
        "Add cascading guides and required fields",
        ["добавили каскадные справочники и обязательные поля в формах;"],
    ),
    (
        "Document project context for Codex",
        ["привели проектную память и правила разработки в порядок;"],
    ),
    (
        "Prepare v0.1.2 release",
        ["подготовили версию 0.1.2 к выпуску;"],
    ),
    (
        "Add save dialogs for archive PDF and CSV",
        ["добавили выбор места сохранения для архива, PDF-буклета и CSV-файлов;"],
    ),
    (
        "Add person folder archive and photo viewer controls",
        ["добавили каталог кавалера, архивирование материалов и удобное управление просмотром фото;"],
    ),
    (
        "Fix mark edit guide preservation",
        ["исправили сохранение справочника знака при редактировании;"],
    ),
    (
        "Make legacy UI single shell and add photo lightbox",
        [
            "убрали лишнюю внешнюю оболочку: основной экран теперь выглядит как единая рабочая программа;",
            "сделали так, что фото открываются крупно прямо на странице, без перехода в отдельный экран;",
        ],
    ),
    (
        "Make legacy UI primary and fix return navigation",
        [
            "сделали основной экран, похожий на старую программу, стартовым при открытии приложения;",
            "исправили возврат назад после добавления и редактирования записей;",
        ],
    ),
    (
        "Stage 3G search rewrite",
        [
            "исправили поиск по фамилиям, названиям и номерам;",
            "добавили понятные условия поиска: везде, по награждённым, по наградам и по знакам;",
        ],
    ),
    (
        "Stage 3F photo viewer and photo management",
        [
            "улучшили просмотр фотографий и работу с фото;",
            "добавили понятные подписи к фотографиям вместо технических названий;",
        ],
    ),
    (
        "Fix Windows media endpoint and rebuild preview",
        ["исправили отображение фотографий на Windows;"],
    ),
    (
        "Fix legacy HEAD support and rebuild Windows preview",
        ["подготовили обновлённый Windows-архив для проверки владельцем;"],
    ),
    (
        "Add Russian help to Windows preview package",
        ["добавили русскую инструкцию для проверки на Windows;"],
    ),
    (
        "Stage 2C Windows portable preview package",
        ["подготовили Windows-архив для проверки без включения данных;"],
    ),
    (
        "Stage 3E legacy desktop layout mirror",
        ["собрали основной экран, похожий на старую Windows-программу;"],
    ),
    (
        "Stage 3D mark CRUD",
        ["добавили кнопки добавления, изменения и удаления для знаков;"],
    ),
    (
        "Stage 3C reward CRUD",
        ["добавили кнопки добавления, изменения и удаления для наград;"],
    ),
    (
        "Stage 3B person CRUD",
        ["добавили кнопки добавления, изменения и удаления для награждённых;"],
    ),
    (
        "Stage 3A backup and write-mode foundation",
        ["добавили защиту: перед изменениями система требует резервную копию;"],
    ),
    (
        "Stage 2B UX readability polish",
        ["улучшили читаемость списков, дат, цен и статусов;"],
    ),
]

TECH_REPLACEMENTS = [
    (re.compile(r"legacy UI", re.IGNORECASE), "основной экран, похожий на старую программу"),
    (re.compile(r"CRUD", re.IGNORECASE), "кнопки добавления, изменения и удаления"),
    (re.compile(r"photo viewer|photo management", re.IGNORECASE), "удобный просмотр фотографий и работа с фото"),
    (re.compile(r"search rewrite", re.IGNORECASE), "исправили поиск по фамилиям, названиям и номерам"),
    (re.compile(r"Windows media fix", re.IGNORECASE), "исправили отображение фотографий на Windows"),
    (re.compile(r"backup/write guard", re.IGNORECASE), "добавили защиту: перед изменениями система требует резервную копию"),
    (re.compile(r"return navigation", re.IGNORECASE), "исправили возврат назад после редактирования"),
    (re.compile(r"lightbox|modal", re.IGNORECASE), "фото открываются крупно прямо на странице"),
    (re.compile(r"Stage\s+\w+", re.IGNORECASE), ""),
    (re.compile(r"workflow|backend|endpoint|route|router|repository|commit|hash|pull|push|SQLite", re.IGNORECASE), ""),
    (re.compile(r"Fedorinov_rewards", re.IGNORECASE), PROJECT_TITLE),
]

RUSSIAN_FALLBACK_ITEMS = [
    "доработали рабочий интерфейс и проверки;",
    "внесли технические улучшения в проект;",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a safe Telegram daily report.")
    parser.add_argument("--date", dest="report_date", help="Report date in YYYY-MM-DD format. Defaults to yesterday.")
    return parser.parse_args(_normalize_argv())


def _normalize_argv() -> list[str] | None:
    import sys

    return [arg.replace("–", "--", 1) if arg.startswith("–") else arg for arg in sys.argv[1:]]


def default_report_date() -> dt.date:
    return dt.date.today() - dt.timedelta(days=1)


def git_subjects_for_date(report_date: dt.date) -> list[str]:
    since = dt.datetime.combine(report_date, dt.time.min).isoformat()
    until = dt.datetime.combine(report_date + dt.timedelta(days=1), dt.time.min).isoformat()
    result = subprocess.run(
        ["git", "log", "--since", since, "--until", until, "--pretty=%s"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _clean_sentence(value: str) -> str:
    text = value.strip()
    for pattern, replacement in TECH_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    text = re.sub(r"\s+", " ", text).strip(" .;,-")
    if not text:
        text = "подготовили очередные улучшения для проверки"
    if not text.endswith((".", ";")):
        text += ";"
    return text


def _contains_latin_letters(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value))


def _fallback_item(index: int) -> str:
    return RUSSIAN_FALLBACK_ITEMS[index % len(RUSSIAN_FALLBACK_ITEMS)]


def _normalize_unknown_subject(subject: str, index: int) -> str:
    cleaned = _clean_sentence(subject)
    if _contains_latin_letters(cleaned):
        return _fallback_item(index)
    return cleaned


def human_items(subjects: list[str]) -> list[str]:
    items: list[str] = []
    for subject in subjects:
        matched = False
        for pattern, replacements in CHANGE_PATTERNS:
            if pattern.lower() in subject.lower():
                items.extend(replacements)
                matched = True
                break
        if not matched:
            items.append(_normalize_unknown_subject(subject, len(items)))

    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean_sentence(item)
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(cleaned)
    return deduped[:8]


def _strip_trailing_semicolon(value: str) -> str:
    return value.rstrip(" ;.") + "."


def validate_text(text: str) -> None:
    lowered = text.casefold()
    for term in BANNED_TERMS:
        if term.casefold() in lowered:
            raise ValueError(f"Report contains forbidden technical wording: {term}")
    forbidden_fragments = ["database/", "Source/", "SourceMark/", ".env"]
    for fragment in forbidden_fragments:
        if fragment in text:
            raise ValueError(f"Report contains forbidden path fragment: {fragment}")


def build_report(report_date: dt.date) -> str:
    subjects = git_subjects_for_date(report_date)
    items = human_items(subjects)
    if not items:
        text = (
            f"Доброе утро!\n\n"
            f"За вчера по проекту “{PROJECT_TITLE}” новых доработок не было.\n\n"
            "Что дальше:\n\n"
            "* продолжаем работу по ближайшим задачам."
        )
        validate_text(text)
        return text

    numbered = "\n".join(f"{index}. {_strip_trailing_semicolon(item)}" for index, item in enumerate(items, start=1))
    checks = [
        "открыть основной экран и убедиться, что он выглядит как единая рабочая программа;",
        "кликнуть по фотографии и проверить, что она открывается крупно прямо на странице;",
        "проверить поиск по фамилии, названию или номеру.",
    ]
    next_steps = [
        "провести пользовательскую проверку и зафиксировать замечания;",
        "после подтверждения собрать следующий пакет для владельца.",
    ]
    text = (
        f"Доброе утро!\n\n"
        f"За вчера по проекту “{PROJECT_TITLE}” сделали:\n\n"
        f"{numbered}\n\n"
        "Что теперь можно проверить:\n\n"
        + "\n".join(f"* {_strip_trailing_semicolon(item)}" for item in checks[:3])
        + "\n\nЧто дальше:\n\n"
        + "\n".join(f"* {_strip_trailing_semicolon(item)}" for item in next_steps[:2])
    )
    validate_text(text)
    return text


def main() -> int:
    args = parse_args()
    report_date = dt.date.fromisoformat(args.report_date) if args.report_date else default_report_date()
    print(build_report(report_date))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
