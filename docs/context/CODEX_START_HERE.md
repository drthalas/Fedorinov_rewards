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

Полные правила ролей, постановки задач, test tiers, Owner QA handoff, статусов и timing telemetry: `docs/context/LINEAR_PROCESS.md`.

Для physical Windows сначала использовать canonical connectivity/access preflight
из `docs/testing/WINDOWS_PHYSICAL_GATE.md`, затем interactive GUI layer из
`docs/WINDOWS_PHYSICAL_GUI_RUNBOOK.md`. Один failed SSH probe не доказывает
offline: обязательна точная классификация discovery, TCP/SSH banner, host key,
service и GUI.

## Шаблон запуска

```text
Перед началом: прочитай docs/context/CODEX_START_HERE.md

Выполни ALE-XXX строго по актуальному Description в Linear.
Description — единственный канонический активный scope.
Accepted / Frozen не переделывать, только проверить на регрессию.
Комментарии использовать как историю и evidence.
Указать branch/base SHA, test tier, time budget, stop condition и required evidence.
```
