# Обязательные инструкции проекта

## Перед началом

1. Прочитать этот файл, `docs/context/CODEX_START_HERE.md` и актуальный Linear Description.
2. Проверить branch, `git status --short` и последние commits.
3. Читать остальные context-файлы только по релевантности задачи; подробная матрица находится в `docs/context/LINEAR_PROCESS.md`.

## Scope и приоритет

- Repo safety/process rules обязательны.
- Актуальный Linear Description — единственный канонический active scope; comments остаются историей и evidence.
- Launch prompt может уточнить или сузить выполнение, но не может расширять scope, противоречить Description или ослаблять safety.
- При конфликте repo rules, Description и prompt остановиться и сообщить о конфликте.
- `Accepted` / `Frozen` не переделывать: разрешены только требуемые regression checks. После owner FAIL в Description остаётся только актуальный defect scope.

## Git и safety

- Работать только в ветке из Description. `main` изменять только отдельной явно разрешённой merge/release-задачей.
- Corrective iteration — новый commit в той же feature-ветке; не amend-ить и не переписывать опубликованную историю.
- Commit/push не являются основанием для `Done`; feature остаётся в `Needs Test` до Owner acceptance.
- Merge, release, version bump, tag, `latest.json`, package publication и Telegram требуют отдельного явного разрешения.
- Не коммитить secrets, `.env`, `.venv`, реальные DB/media, `Source`, `SourceMark`, `default`, backups, screenshots, Playwright output, logs, temp archives и generated artifacts.
- Write/destructive tests выполнять только на temp DB/media. Не запускать real updater apply и не менять пользовательские данные без отдельного разрешения.

## Проверки и отчёт

- Соблюдать test tier, time budget и stop condition. Codex не меняет Owner-selected model/reasoning effort в UI.
- Для локального web UI browser/Playwright click-flow обязателен по tier; unit tests, mocks и прямые JS-вызовы не заменяют browser acceptance. Computer Use — только optional diagnostic fallback.
- Runtime identity и `OWNER QA URL` обязательны только для локально запускаемой web UI feature-задачи. Для native/packaged/embedded flow честно указать `not applicable` или `not tested` и дать точную Owner retest instruction.
- Safety hashes включать в отчёт только при T4, migrations, destructive/write flow, риске real data/media или явном требовании Description.
- Подробные роли, test tiers, runtime handoff, статусы и timing telemetry определены в `docs/context/LINEAR_PROCESS.md`.
