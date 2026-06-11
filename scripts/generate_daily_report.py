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
    "fallback",
    "unknown changes",
    "technical changes without description",
    "commit не распознан",
    "есть изменения без пользовательского описания",
    "перед проверкой нужно уточнить их смысл",
]

CHANGE_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "Fix daily report fallback wording",
        ["исправили ежедневный отчёт: служебные диагностические фразы больше не попадают в сообщение владельцу;"],
    ),
    (
        "Prepare v0.1.4 release",
        [
            "подготовили и выпустили релиз v0.1.4;",
            "проверили пакет обновления и основные сценарии перед уведомлением владельцу;",
            "обновили задачи в Linear после релиза;",
        ],
    ),
    (
        "Fix daily report factual summaries",
        ["исправили ежедневный отчёт: он должен показывать конкретные факты, а не общие фразы;"],
    ),
    (
        "Polish owner feedback rewards screen",
        ["улучшили главный экран и карточку кавалера по замечаниям владельца;"],
    ),
    (
        "Improve summary filters and sorting",
        ["улучшили сводную таблицу: добавили каскадные фильтры и сортировку;"],
    ),
    (
        "Improve search award results",
        ["улучшили поиск по наградам: добавили поиск по номеру и новые колонки с фото/документами;"],
    ),
    (
        "Save pasted photos as JPEG",
        ["исправили вставку фото из буфера: теперь изображения сохраняются в JPEG;"],
    ),
    (
        "Fix owner feedback layout blockers",
        ["исправили найденные при проверке проблемы с прокруткой списка и компактностью формы;"],
    ),
    (
        "Fix daily report Russian wording",
        ["исправили ежедневный Telegram-отчёт: текст теперь формируется на русском языке;"],
    ),
    (
        "Polish rewards screen layout",
        [
            "улучшили главный экран “Награды”: список кавалеров отсортирован по алфавиту, появился быстрый поиск, а перечень наград прокручивается внутри своего блока;",
        ],
    ),
    (
        "Improve person creation flow",
        [
            "улучшили добавление кавалера: после создания сразу открывается экран, где можно добавить фотографии и документы;",
        ],
    ),
    (
        "Improve reward creation flow",
        [
            "улучшили добавление награды: после сохранения сразу можно добавить фотографии и документы награды;",
        ],
    ),
    (
        "Polish person card layout",
        [
            "улучшили карточку кавалера: длинные ФИО, ссылки, биография и комментарии аккуратно переносятся;",
        ],
    ),
    (
        "Prepare final v0.1.2 release",
        ["подготовили финальный релиз v0.1.2;"],
    ),
    (
        "Clarify v0.1.2 Windows Save As testing",
        ["уточнили проверку сохранения файлов на Windows Chrome/Edge для владельца;"],
    ),
    (
        "Fix photo frame sizing",
        [
            "исправили отображение фото: реальные фотографии и блоки “Нет фото” теперь находятся в одинаковых рамках;",
        ],
    ),
    (
        "Fix legacy photo frame layout",
        [
            "исправили отображение фото: реальные фотографии и блоки “Нет фото” теперь находятся в одинаковых рамках;",
        ],
    ),
    (
        "Add summary PDF export",
        ["добавили PDF-экспорт для сводной таблицы и шахматки;"],
    ),
    (
        "Prepare v0.1.3 release",
        [
            "подготовили и выпустили релиз v0.1.3;",
            "проверили пакет обновления и основные сценарии перед уведомлением владельцу;",
            "обновили задачи в Linear после релиза;",
        ],
    ),
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
    "вчера были изменения в проекте, но автоматический отчёт не смог точно определить пользовательское описание. Нужно сверить журнал разработки;",
]

CHECK_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "Fix daily report fallback wording",
        ["проверить dry-run ежедневного отчёта: в сообщении не должно быть служебных диагностических фраз;"],
    ),
    (
        "Prepare v0.1.4 release",
        ["проверить обновление через кнопку и убедиться, что приложение видит версию v0.1.4;"],
    ),
    (
        "Fix daily report factual summaries",
        ["проверить dry-run ежедневного отчёта: он должен показывать конкретные факты за день;"],
    ),
    (
        "Polish owner feedback rewards screen",
        ["проверить главный экран “Награды” и удержание выбранного кавалера в списке;"],
    ),
    (
        "Improve summary filters and sorting",
        ["проверить сводную таблицу, каскадные фильтры и сортировку;"],
    ),
    (
        "Improve search award results",
        ["проверить поиск по номеру награды и новые фото/документные колонки;"],
    ),
    (
        "Save pasted photos as JPEG",
        ["проверить вставку фото из буфера и сохранение в JPEG;"],
    ),
    (
        "Fix owner feedback layout blockers",
        ["проверить компактную форму редактирования кавалера и видимость выбранной строки в списке;"],
    ),
    (
        "Fix daily report Russian wording",
        ["проверить dry-run ежедневного отчёта: текст должен быть на русском и без английских технических строк;"],
    ),
    (
        "Polish rewards screen layout",
        [
            "проверить главный экран “Награды”: сортировку кавалеров, быстрый поиск слева и внутренний скролл перечня наград;",
        ],
    ),
    (
        "Improve person creation flow",
        ["проверить добавление кавалера: после создания должны быть доступны фото, документы и переход к наградам;"],
    ),
    (
        "Improve reward creation flow",
        ["проверить добавление награды: после сохранения должны быть доступны фото, документы и добавление следующей награды;"],
    ),
    (
        "Polish person card layout",
        ["проверить карточку кавалера: длинные ФИО, ссылки, биография и комментарии должны переноситься корректно;"],
    ),
    (
        "Clarify v0.1.2 Windows Save As testing",
        ["проверить выбор места сохранения на Windows Chrome/Edge;"],
    ),
    (
        "Fix photo frame sizing",
        ["проверить, что фото и “Нет фото” отображаются в одинаковых рамках;"],
    ),
    (
        "Fix legacy photo frame layout",
        ["проверить, что фото и “Нет фото” отображаются в одинаковых рамках;"],
    ),
    (
        "Add summary PDF export",
        ["проверить PDF на вкладке “Свод.таблица”: свод по наградам и шахматку по кавалерам;"],
    ),
    (
        "Prepare v0.1.3 release",
        ["проверить обновление через кнопку и убедиться, что приложение видит версию v0.1.3;"],
    ),
    (
        "Prepare final v0.1.2 release",
        ["проверить обновление через кнопку и убедиться, что приложение видит версию v0.1.2;"],
    ),
    (
        "Implement browser Save As for exports",
        ["проверить сохранение архива, PDF и CSV через окно выбора места сохранения;"],
    ),
]

NEXT_STEP_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "Prepare v0.1.4 release",
        [
            "проверка владельцем после v0.1.4;",
            "собрать замечания владельца и перевести их в Linear-задачи;",
        ],
    ),
    (
        "Prepare v0.1.3 release",
        [
            "проверка владельцем после v0.1.3;",
            "собрать замечания владельца и перевести их в Linear-задачи;",
        ],
    ),
    (
        "Prepare final v0.1.2 release",
        [
            "проверка владельцем после v0.1.2;",
            "собрать замечания владельца и перевести их в Linear-задачи;",
        ],
    ),
    (
        "Add summary PDF export",
        ["передать PDF-экспорт сводной таблицы на QA;"],
    ),
    (
        "Fix legacy photo frame layout",
        ["передать исправление фото-фреймов на QA;"],
    ),
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
    matched_items: list[str] = []
    unknown_items: list[str] = []
    for subject in subjects:
        matched = False
        for pattern, replacements in CHANGE_PATTERNS:
            if pattern.lower() in subject.lower():
                matched_items.extend(replacements)
                matched = True
                break
        if not matched:
            normalized = _normalize_unknown_subject(subject, len(unknown_items))
            unknown_items.append(normalized)

    items = matched_items[:]
    if not matched_items and unknown_items:
        items.append(unknown_items[0])
    elif matched_items:
        items.extend(item for item in unknown_items if item not in RUSSIAN_FALLBACK_ITEMS)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean_sentence(item)
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(cleaned)
    return deduped[:8]


def _dedupe_sentences(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = _clean_sentence(item)
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def _items_from_patterns(subjects: list[str], patterns: list[tuple[str, list[str]]], limit: int) -> list[str]:
    items: list[str] = []
    for subject in subjects:
        for pattern, replacements in patterns:
            if pattern.lower() in subject.lower():
                items.extend(replacements)
                break
    return _dedupe_sentences(items, limit)


def check_items(subjects: list[str], report_items: list[str]) -> list[str]:
    checks = _items_from_patterns(subjects, CHECK_PATTERNS, 4)
    if checks:
        return checks
    if report_items and all(item in RUSSIAN_FALLBACK_ITEMS for item in report_items):
        return [
            "сверить журнал разработки и уточнить, какие изменения нужно проверить;",
        ]
    return _dedupe_sentences(
        [f"проверить: {_strip_trailing_semicolon(item)}" for item in report_items[:3]],
        3,
    )


def next_step_items(subjects: list[str]) -> list[str]:
    release_subjects = [subject for subject in subjects if "release" in subject.lower()]
    if release_subjects:
        release_steps = _items_from_patterns(release_subjects, NEXT_STEP_PATTERNS, 3)
        if release_steps:
            return release_steps
    next_steps = _items_from_patterns(subjects, NEXT_STEP_PATTERNS, 3)
    if next_steps:
        return next_steps
    return [
        "провести пользовательскую проверку и зафиксировать замечания;",
        "следующие замечания оформить отдельными задачами в Linear;",
    ]


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
    checks = check_items(subjects, items)
    next_steps = next_step_items(subjects)
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
