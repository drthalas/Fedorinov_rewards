# Codex: стартовый файл проекта

## Всегда перед задачей

1. Прочитать `AGENTS.md`, этот файл и актуальный Linear Description.
2. Проверить branch, `git status --short` и последние commits.
3. Сверить branch/base SHA, active scope, `Accepted` / `Frozen`, Out of Scope, test tier, time budget и stop condition.

Не перечитывать всю историю проекта для T0/T1 без необходимости. Остальные context-файлы читать по релевантности:

- product/code: `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `QA_NOTES.md`;
- release: `RELEASES.md`, `CHANGELOG.md`;
- process/docs/merge/diagnostic: только нужные process/release-файлы, прежде всего `LINEAR_PROCESS.md`.

## Приоритет и безопасность

- Repo safety/process rules обязательны; актуальный Linear Description — канонический active scope.
- Launch prompt может только уточнить или сузить работу. Он не может расширять scope, противоречить Description или ослаблять safety.
- При конфликте остановиться и сообщить о нём, не угадывать.
- Не трогать реальные DB/media и не коммитить secrets, `.env`, `.venv`, DB/media, backups, logs, screenshots или generated artifacts без явного разрешения.
- Merge, release, version/tag, `latest.json`, package publication, Telegram и real updater apply разрешены только отдельным актуальным Description.
- В release/Telegram-инструкциях штатный post-update сценарий — автоматический перезапуск; `start_windows.bat` указывать только как fallback, если приложение не открылось самостоятельно.

## Краткий workflow

- Owner выбирает model/reasoning в UI; ChatGPT даёт Owner human-facing рекомендацию до запуска; Codex модель сам не переключает.
- Для local web UI использовать browser/Playwright first; Computer Use — optional fallback. Native/packaged/embedded flow без доступного branch runtime отмечать `not applicable` / `not tested` с точной Owner retest instruction.
- Runtime identity и `OWNER QA URL` требуются только для локально запускаемых web UI feature-задач.
- Соблюдать назначенный tier и budget; full suite запускать только когда он требуется scope/tier, а не после каждой iteration.
- Windows VM остаётся development/test-контуром feature-задач по их tier. Если product change уже прошёл требуемый VM gate и Owner acceptance на physical Windows, release stage не повторяет полный VM updater gate по умолчанию.
- После controlled merge exact release package из merged `main` до publication проверяется один раз на physical Windows по пути current public -> candidate. Pre-merge Owner acceptance не заменяет этот exact-artifact gate.
- Rollback/forced-failure на release stage обязателен только для изменений updater/recovery либо по явному требованию Owner.
- На physical Windows постоянная Desktop-папка `Fedorinov Rewards - Public Current` содержит только текущую опубликованную production-версию. Candidate разворачивать отдельно и никогда не заменять эту baseline-папку до publication.

Полные правила ролей, постановки задач, test tiers, Owner QA handoff, статусов и timing telemetry: `docs/context/LINEAR_PROCESS.md`.

## Шаблон запуска

```text
Перед началом: прочитай docs/context/CODEX_START_HERE.md

Выполни ALE-XXX строго по актуальному Description в Linear.
Description — единственный канонический активный scope.
Accepted / Frozen не переделывать, только проверить на регрессию.
Комментарии использовать как историю и evidence.
Указать branch/base SHA, test tier, time budget, stop condition и required evidence.
```
