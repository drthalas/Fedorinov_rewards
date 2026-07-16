# Linear process

## Проект и язык

Linear project:

```text
Кавалеры и награды
```

Все пользовательские titles, descriptions, checklists и comments вести на русском языке. Английский допустим для commit hash, URLs, repository names, branch names и технических идентификаторов.

## Канонический scope и приоритет

- Repo safety/process rules обязательны.
- Актуальный Linear Description — единственный канонический active scope.
- Comments содержат историю, отчёты и evidence и не добавляют новый scope, если Description прямо не говорит обратного.
- `Accepted` / `Frozen` не переделывать; для них выполнять только требуемые regression checks.
- После Owner FAIL обновить Description: оставить актуальные дефекты, принятую часть перенести в `Accepted` / `Frozen`, а несвязанное требование оформить отдельной issue.
- Launch prompt может уточнить или сузить выполнение, но не может расширять scope, противоречить Description или ослаблять repo safety. При конфликте Codex останавливается и сообщает о нём.

## Роли и запускной prompt

### Owner

- Вручную выбирает model и reasoning effort в интерфейсе до запуска Codex.
- Не должен угадывать runtime, порт или соответствующую commit SHA вкладку во время QA.

### ChatGPT-координатор

- Перед каждым запускным prompt сообщает Owner: сложность `XS/S/M/L/XL`, рекомендуемую модель, reasoning effort, test tier, ожидаемое время и stop condition.
- Это human-facing рекомендация, а не команда Codex самостоятельно менять модель в UI.
- В обычном чате ChatGPT не читает локальные repo-файлы автоматически: он опирается на согласованный project context и при необходимости отдельно читает или обновляет документы доступными инструментами.

### Codex

- Выполняет задачу на выбранной Owner модели и не пытается менять model/reasoning effort в UI.
- Соблюдает active scope, tier, time budget, stop condition и safety. При превышении сложности не расширяет работу бесконтрольно, а возвращает blocker или конкретное объяснение задержки.

Запускной prompt должен быть конкретным и самодостаточным: branch/base SHA, точные действия, `Accepted` / `Frozen`, Out of Scope, required evidence, test tier, time budget и stop condition. Для corrective и сложных UI-багов недостаточно фразы «прочитай Linear и сделай».

## Контекст перед задачей

Всегда читать:

1. `AGENTS.md`;
2. `docs/context/CODEX_START_HERE.md`;
3. актуальный Linear Description.

Дальше читать только релевантные context-файлы:

- product/code: `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `QA_NOTES.md`;
- release: `RELEASES.md`, `CHANGELOG.md`;
- process/docs/merge/diagnostic: соответствующие process/release-файлы.

Для T0/T1 не перечитывать всю историю проекта без необходимости. Перед изменениями проверить branch, clean working tree, base/head и ограничения задачи.

## Test tiers

### T0 Diagnostic

Только необходимые команды и один smoke. Без product code changes, full suite, compileall, Goal Loop и повторного safety audit. Бюджет: 3–10 минут.

### T1 Merge/docs

Ancestry, local/remote parity, clean tree, `git diff --check` и разрешённый список файлов. Product tests не повторять, Goal Loop не использовать. Бюджет: 3–20 минут.

### T2 Narrow fix

Focused tests и один узкий reproduction, зависящий от поверхности:

- UI/browser: browser click-flow;
- backend-only: focused integration tests.

Full suite — один раз после стабилизации, если он требуется scope/tier. Goal Loop максимум 2 итерации. Бюджет: 20–45 минут.

### T3 Cross-flow UI

Focused tests, browser E2E всех затронутых UI flows, full suite один раз перед final commit, runtime identity и Owner QA handoff для локально запускаемого web UI. Goal Loop максимум 3 итерации. Бюджет: 45–90 минут.

### T4 Data/media

Добавляет data/media safety к релевантному T2 или T3: temp DB/media, destructive/shared-reference tests, failure safety и реальные DB/media hashes при реальном риске или явном требовании. Не требует browser/runtime для чисто non-UI data task. Goal Loop максимум 3 итерации. Бюджет: 60–120+ минут.

Не запускать full suite после каждой Goal Loop iteration: во время разработки использовать focused checks, а full suite запускать один раз после финальной стабилизации, если его требует scope/tier.

## Browser-first UI QA

Для локального web UI основной путь — built-in browser / Playwright headed E2E. UI PASS требует реальный click-flow, фактический результат после reload, console/network/application HTTP checks и screenshots, когда они нужны для visual evidence.

File upload/source selection проверять реальными `filechooser`/file input events с temp fixtures. Unit tests, mocks, source ordering и прямые JavaScript-вызовы не заменяют browser acceptance.

Computer Use — только optional diagnostic fallback: best effort, non-blocking, не обязательный QA/release gate и не единственное evidence PASS. Human-required native шаги нельзя называть автономным PASS.

## Runtime identity и Owner QA handoff

Runtime identity и блок `OWNER QA URL` обязательны только для feature-задачи с локально запускаемым web UI runtime.

Перед переводом такой задачи в `Needs Test`:

1. Зафиксировать branch и полный final SHA.
2. Запустить свежий QA runtime после checkout этого SHA на отдельном порту.
3. Указать exact URL, PID, start time и `TEMP`/`REAL` DB/media.
4. Подтвердить identity через startup log, cache key, HTML marker или другой воспроизводимый механизм без UI clutter.
5. Выполнить browser smoke с того же URL, который передаётся Owner.
6. Не смешивать write QA real-data и temp runtime без явного разделения процессов, портов и safety baseline.
7. Оставить проверенный QA runtime запущенным для Owner.

Финальный отчёт и Linear comment должны содержать `OWNER QA URL`: один clickable URL, port, PID, start time, branch, полный SHA, TEMP/REAL DB/media, старые URL/порты, которые нельзя использовать, 3–7 коротких шагов и подтверждение, что runtime оставлен запущенным.

Для native, packaged или embedded flow, когда branch runtime нельзя запустить локально, указать `not applicable` или `not tested`, дать точную Owner retest instruction и не заявлять косвенный PASS. Не требовать невозможный localhost URL только для перехода в `Needs Test`.

## Git, статусы и Owner QA

- Работать только в ветке из Description. `main` изменять только отдельной явно разрешённой merge/release-задачей.
- Corrective iteration — отдельный commit в той же feature-ветке; не amend-ить и не переписывать опубликованную историю.
- Commit/push переводят feature-задачу в `Needs Test`, но не в `Done`.
- Owner PASS означает, что feature принята и может быть переведена в `Done`, если в ней не осталось feature work. При необходимости после этого создаётся или авторизуется отдельная controlled merge issue.
- Owner FAIL переводит issue в `Needs Fix`; corrective commit не заменяет acceptance.
- Не переводить каждую feature автоматически в «Готово к релизу»: merge и release остаются отдельными контролируемыми задачами с явным authorization.

После commit/push добавить Linear comment: что сделано, commit hash, проверки, ограничения и Owner QA steps. Для UI включить browser evidence и runtime handoff, если они применимы.

## Релизы и Owner проверка

Merge и release — отдельные issue и выполняются только при явном Owner authorization в актуальном Description. Version bump, tag, GitHub Release, `latest.json`, package publication и Telegram не выполнять в feature/bug issue без отдельного разрешения.

После релиза создать или обновить Owner QA issue с проверкой обновления, новых функций, рабочей записи и замечаний. После Owner acceptance связанные задачи можно переводить в `Done` по их фактическому scope.

## Timing telemetry

В финальном отчёте указывать длительность применимых этапов: investigation, implementation, focused tests, browser E2E, full suite, safety checks, commit/push и runtime handoff. Неприменимое отмечать `not run` или `n/a`.

Если работа превышает ожидаемый бюджет более чем в 1.5 раза, не расширять scope, не начинать новые широкие проверки и не повторять full suite без причины: вернуть blocker или конкретное объяснение задержки.
