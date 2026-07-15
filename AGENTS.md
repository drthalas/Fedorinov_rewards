# Обязательные инструкции проекта

## Перед началом

1. Всегда сначала прочитать `docs/context/CODEX_START_HERE.md` и указанные там context-файлы.
2. Проверить текущую ветку, `git status --short` и последние commits.
3. Открыть текущую Linear issue и работать только в рамках её актуального Description.

## Канонический scope

- Актуальный Linear Description — единственный канонический активный scope задачи.
- Linear comments используются как история, отчёты и evidence, если Description явно не говорит обратного.
- Разделы `Accepted` / `Frozen` не переделывать. Для них разрешены только regression checks.
- После owner FAIL в Description должен остаться только актуальный defect scope, а принятые части должны быть перенесены в `Accepted` / `Frozen`.
- Новую несвязанную область оформлять отдельной Linear issue.

## Git и статусы

- Работать только в ветке, указанной в Description. Не изменять `main` напрямую без явной merge/release-задачи.
- Corrective iteration делать отдельным commit в той же feature-ветке. Не amend-ить и не переписывать опубликованную историю.
- Commit и push не означают `Done`: feature-задачу оставить в `Needs Test`, owner фиксирует acceptance.
- Merge и release являются отдельными контролируемыми шагами и требуют явного owner authorization.
- Не выполнять version bump, tag, release, изменение `latest.json`, package publication или Telegram без отдельного разрешения.

## Проверки и evidence

- UI-задача не считается готовой только по unit tests или mocks. Нужны реальный visible click-flow, фактический результат, reload, regression checks и screenshots/evidence по scope.
- Если native OS или packaged runtime не проверялись, явно написать `not tested` / `owner retest required`; не заявлять `PASS` по косвенным тестам.
- Destructive/write tests выполнять только на temp DB и temp media. Реальные пользовательские DB, фото и документы не изменять.

## Safety

- Не коммитить secrets, `.env`, `.venv`, реальные DB/media, `Source`, `SourceMark`, `default`, backups, screenshots, Playwright output, logs, temp archives и generated artifacts.
- Не запускать real updater apply и не менять пользовательские данные без отдельного разрешения.
- Не выводить токены и другие credentials в terminal output, документацию или Linear.

## Итоговый отчёт

Указать branch, initial/final HEAD, commit, push и local/remote parity, tests, browser/runtime evidence, limitations, safety hashes и итоговый `git status`.
