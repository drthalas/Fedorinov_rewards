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
- Первый запуск постоянной Owner-установки выполняется существующим пользовательским `Start.bat`. После обновления штатен автоматический restart; `start_windows.bat` — только fallback, если приложение не открылось. Не пересоздавать Public Current или BAT.

## Краткий workflow

Owner workflow: [утверждённый документ Linear](https://linear.app/drthalas/document/owner-workflow-physical-windows-runtime-i-release-candidate-cherez-990849969b4b). Подробности: [LINEAR_PROCESS.md](LINEAR_PROCESS.md#owner-workflow-по-фазам) и [RELEASES.md](RELEASES.md#актуальный-workflow).

1. Implementation и focused TEMP tests → отдельно разрешённый feature preview на физическом Windows `COPEW-04C68047F`, с согласованным прежним рабочим SQLite/media profile. При запросе «запусти runtime/покажи preview» Owner ожидает этот Windows и открытый Edge; Mac/VM smoke его не заменяет. Автоматические write-тесты — только TEMP; Public Current не затрагивать.
2. Owner feature PASS → отдельно разрешённый exact candidate packaging на Mac из принятого HEAD в feature/release branch: package/version/SHA/byte parity, Owner-only channel только при разрешении → **STOP**. Не подключаться к Windows, не запускать runtime/Edge/updater и не менять `.env` в packaging-фазе. Включение более позднего docs-only commit в candidate требует явного Owner разрешения.
3. Отдельный Windows updater handoff → постоянный Public Current, существующий `Start.bat` → «О программе → Проверить обновления → Обновить». Подтвердить candidate visibility; при необходимости менять только `UPDATE_MANIFEST_URL` по отдельному разрешению. Updater и product review выполняет Owner.
4. Явный Owner updater/product PASS → отдельно разрешённый controlled merge exact accepted HEAD в `main` → production GitHub Release / public `latest.json`. При FAIL/паузе candidate не попадает в main/production.
5. После проверки production и отдельного разрешения — Telegram **Сергею и Owner**. Нужны два отдельных подтверждения Telegram API со статусом и `message_id` по ролям; один primary `message_id` не означает общий PASS. Missing recipient → preflight FAIL до отправки; partial failure → повтор только неуспешному адресату без дублей. Реализация этого контракта — отдельная [ALE-502](https://linear.app/drthalas/issue/ALE-502/release-telegram-obyazatelnoe-uvedomlenie-owner-i-sergeya-s-razdelnym).

Owner выбирает model/reasoning в UI; ChatGPT до запуска даёт human-facing рекомендацию, Codex настройки не переключает. Browser/Playwright click-flow обязателен по назначенному tier; Computer Use — optional diagnostic fallback. Для web UI передать identity и `OWNER QA URL` физического Windows и оставить Edge/runtime работающими. Для docs-only runtime handoff — `n/a`; для неприменимых native/embedded сценариев — `not applicable` / `not tested` с точной retest instruction.

Соблюдать tier/budget и stop condition. После feature PASS не повторять full suite/VM/physical feature acceptance без конкретного blocker или риска updater/recovery/packaging/migration; смена фазы сама по себе не добавляет gate. Внутренний Codex QA PASS не заменяет ни один Owner PASS.

## Шаблон запуска

```text
Перед началом: прочитай docs/context/CODEX_START_HERE.md

Выполни ALE-XXX строго по актуальному Description в Linear.
Description — единственный канонический активный scope.
Accepted / Frozen не переделывать, только проверить на регрессию.
Комментарии использовать как историю и evidence.
Указать branch/base SHA, test tier, time budget, stop condition и required evidence.
```
