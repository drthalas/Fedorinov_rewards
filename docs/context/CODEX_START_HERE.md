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
- Candidate и production требуют явного Owner разрешения в scope задачи. После Owner updater/product PASS команда «выпускаем релиз» разрешает controlled merge, публикацию exact принятого ZIP и штатный Telegram обоим в одном production execution, без повторных разрешений на эти действия. Обновление candidate через updater выполняет Owner.
- Первый запуск постоянной Owner-установки выполняется фактически существующим пользовательским BAT в Public Current; имя и путь подтвердить на physical Windows (по handoff v2.0.27 — `start_windows.bat`). После обновления штатен автоматический restart; ручной повторный запуск этого BAT — только fallback, если приложение не открылось. Не пересоздавать Public Current или BAT.

## Краткий workflow

**implementation → physical Windows runtime → Owner feature PASS → Owner candidate с обновлением через существующий BAT → Owner updater/product PASS → production + Telegram обоим.**

Основание: [Owner workflow](https://linear.app/drthalas/document/owner-workflow-physical-windows-runtime-i-release-candidate-cherez-990849969b4b) с уточнениями Owner от 19.10.2026 в [ALE-507](https://linear.app/drthalas/issue/ALE-507/owner-candidate-v2028-ale-503504505-ale-506) и [ALE-502](https://linear.app/drthalas/issue/ALE-502/release-telegram-obyazatelnoe-uvedomlenie-owner-i-sergeya-s-razdelnym). Подробности: [LINEAR_PROCESS.md](LINEAR_PROCESS.md#owner-workflow-по-фазам) и [RELEASES.md](RELEASES.md#актуальный-workflow).

1. Implementation и проверки по tier; автоматические write-тесты только на TEMP SQLite/media.
2. Показать реализацию на физическом Windows `COPEW-04C68047F`: согласованный рабочий SQLite/media profile, отдельный runtime и открытый Edge. Mac/VM smoke не заменяет этот preview. Дождаться Owner feature PASS; Public Current не затрагивать при feature preview.
3. Подготовить Owner candidate из принятого HEAD в feature/release branch. Внутри одной candidate-задачи сначала собрать/проверить exact ZIP на Mac, затем выполнить разрешённый Windows handoff к постоянному Public Current и фактически существующему пользовательскому BAT → «О программе → Проверить обновления → Обновить». Не пересоздавать установку/BAT; при необходимости менять только разрешённый `UPDATE_MANIFEST_URL`. Packaging не выполняет Windows-действий. Если prompt ограничен Mac-only packaging, STOP `CANDIDATE PUBLISHED — WINDOWS HANDOFF PENDING`; если handoff уже разрешён, продолжить его без нового продуктового этапа или повторного разрешения.
4. Owner лично обновляет постоянную установку и проводит product review. После явного Owner updater/product PASS и команды «выпускаем релиз» Codex выполняет весь production execution.
5. Controlled merge exact accepted HEAD в main → GitHub Release/public `latest.json` из того же принятого ZIP без пересборки → public SHA/size/byte parity → автоматически штатное Telegram-уведомление **Сергею и Owner** с действующей конфигурацией. Проверить получателей и существующую production-историю этой версии, не повторять известные успешные отправки, зафиксировать два API `message_id`/статуса. Не требовать отдельного разрешения на Telegram, нового общего журнала, integration ALE-502, веток или тестов. При реальной неоднозначности получателя/истории или API FAIL — конкретный blocker/partial FAIL без слепого повтора.

Внутренние packaging/handoff — безопасное разделение работы Codex внутри подготовки candidate, а не новые Owner acceptance stages. Не выдавать опубликованный ZIP за готовность к ручному обновлению без подтверждённой Windows visibility. Feature PASS и updater/product PASS сохраняются; при FAIL candidate не попадает в main/production. Docs-only commits после принятого HEAD не включать в candidate автоматически.

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
