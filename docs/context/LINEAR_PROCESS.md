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

Для Tier 1 не перечитывать всю историю проекта без необходимости. Перед изменениями проверить branch, clean working tree, base/head и ограничения задачи.

## Test tiers

Актуальный Linear Description назначает ровно один Tier 1–4 и объясняет любое повышение. Codex не повышает Tier самостоятельно из осторожности. Если в ходе работы доказан новый риск, остановиться и предложить изменение Description, а не молча расширять проверки.

| Tier | Когда применять | Обязательно | По умолчанию не выполнять |
| --- | --- | --- | --- |
| **Tier 1 — малый риск** | Docs/process, merge, локальное UI/CSS/asset или другое узкое изменение без data/runtime риска | Focused или docs checks; применимые syntax/compile; один browser smoke для UI; full suite один раз перед сдачей product code | Sergey-full VM, physical Windows, broad DB/media fingerprints, updater/recovery, full dataset copy/reset |
| **Tier 2 — обычная продуктовая логика** | Обычный backend/frontend flow без migration, platform lifecycle или scale-specific риска | Focused и связанные regressions; full suite один раз; headed browser на synthetic-small или уже существующем fixture | Обязательный Sergey-full VM, автоматический physical gate, broad fingerprints, full dataset copy/reset |
| **Tier 3 — высокий продуктовый риск** | Media lifecycle, scale/performance, Windows-specific behavior, migrations, rollback | Focused/regression tests; full suite один раз; Windows VM с постоянным Sergey fixture; integrity/fingerprint только затронутой области | Physical Windows без доказанной Windows-specific причины или явного Owner gate; глобальные fingerprints; per-task full copy/reset |
| **Tier 4 — release/updater/recovery** | Exact release candidate, updater, recovery, launcher/runtime lifecycle | Полный exact-user updater/recovery gate на Windows VM; package/SHA/BAT/startup/reboot/data-preservation checks; ручной Owner updater gate на physical Windows | Автоматический полный updater flow Codex на physical; публикация до Owner PASS; изменение immutable backup/master fixture |

Для docs-only и merge-only Tier 1 product full suite, compile и browser отмечать `n/a`, если они не затронуты. Для product code full suite запускается один раз после стабилизации, а не после каждой iteration. Во время разработки использовать только быстрые focused checks.

## Постоянный Sergey fixture на Windows VM

- Существующий Sergey dataset на Windows VM — постоянный mutable расходный fixture, а не актуальная production-копия.
- На fixture разрешены create/edit/delete, media mutations и необратимые тестовые действия в рамках назначенного Tier.
- Не создавать отдельную full DB/media-копию для каждой задачи и не выполнять reset/restore после каждой задачи.
- Backup/restore разрешён только если fixture повреждён, нужна доказуемо чистая baseline-проверка или выполняется exact updater/recovery test.
- Не плодить full-size transport, run или safety-копии. Использовать существующий fixture root; локальные пути и приватную структуру данных не коммитить и не публиковать.
- Для быстрых Tier 1–2 проверок использовать synthetic-small или уже существующий лёгкий fixture. Sergey-full подключать только когда это требует Tier/Description.
- Integrity и fingerprints считать только по затронутой области, если Description не требует полный release/data gate.
- Physical Windows не является второй автоматической копией VM workflow. Это production-like ручной Owner gate по правилам Tier 4 или отдельному явному Description.

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

Для Tier 4 Codex сначала выполняет полный exact-user updater/recovery gate на Windows VM. Затем Owner вручную проверяет exact candidate на physical Windows теми же действиями, что доступны пользователю: запускает текущий штатный BAT, видит candidate и нажимает «Обновить». Codex не запускает candidate заранее, не подменяет вручную файлы и не выполняет скрытые действия, отсутствующие у пользователя.

Production GitHub Release, `latest.json`, Telegram и доступность обновления разрешены только после ручного Owner PASS и отдельной команды. Пока updater не доказал стабильность на нескольких релизах, полный VM gate обязателен.

## Timing telemetry

В финальном отчёте указывать длительность применимых этапов: investigation, implementation, focused tests, browser E2E, full suite, safety checks, commit/push и runtime handoff. Неприменимое отмечать `not run` или `n/a`.

Если работа превышает ожидаемый бюджет более чем в 1.5 раза, не расширять scope, не начинать новые широкие проверки и не повторять full suite без причины: вернуть blocker или конкретное объяснение задержки.
