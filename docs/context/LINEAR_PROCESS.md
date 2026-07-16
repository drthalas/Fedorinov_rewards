# Linear process

## Проект

Linear project:

```text
Кавалеры и награды
```

Все пользовательские названия задач, описания, чек-листы и комментарии вести на русском языке.

## Scope и источники evidence

- Актуальный Description issue — единственный канонический активный scope.
- Comments хранят историю, отчёты и evidence и не добавляют новый scope, если Description явно не говорит обратного.
- `Accepted` / `Frozen` не переделывать; для них выполняются только regression checks.
- После owner FAIL обновить Description: оставить актуальные дефекты, а принятую часть перенести в `Accepted` / `Frozen`.
- Несвязанное новое требование оформлять отдельной issue.

## Роли и запускной prompt

### Owner

- Вручную выбирает модель и reasoning effort в интерфейсе перед запуском Codex.
- Репозиторные инструкции, Linear Description и запускные prompt не должны утверждать, что Codex сам переключает модель в UI.

### ChatGPT-координатор

- Перед выдачей каждого запускного prompt сообщает Owner: сложность `XS/S/M/L/XL`, рекомендуемую модель, рекомендуемый reasoning effort, test tier, ожидаемое время и stop condition.
- Это human-facing рекомендация Owner, а не команда Codex самостоятельно менять модель.
- В обычном чате ChatGPT не читает локальные repo-файлы автоматически: он опирается на согласованный project context и при необходимости отдельно читает или обновляет документы доступными инструментами.

### Codex

- Выполняет задачу на модели, выбранной Owner, и не пытается менять её в UI.
- Соблюдает active scope, test tier, time budget, stop condition и safety. Если задача фактически сложнее заявленной, сообщает об этом и останавливается по stop condition, а не расширяет scope бесконтрольно.

Запускной prompt из ChatGPT должен быть конкретным и самодостаточным: branch/base SHA, точные действия, Accepted/Frozen, Out of Scope, required evidence, test tier, time budget и stop condition. Для corrective и сложных UI-багов недостаточно фразы «прочитай Linear и сделай».

## Соответствие статусов

Если в Linear доступны только системные статусы, использовать ближайшие соответствия:

- Backlog = Бэклог.
- Todo / Ready for Codex = Готово к работе.
- In Codex / In Progress = В работе.
- Needs Review / Needs Test / Ready to Commit = Готово к QA или на тестировании.
- Needs Fix = QA не пройден.
- In Review = Проверка владельцем или ревью.
- Done = Завершено / Выпущено.
- Blocked = Заблокировано.

Если в конкретной задаче статус нужен точнее, объяснить это в комментарии.

## Перед задачей

Codex должен:

1. Прочитать `docs/context/CODEX_START_HERE.md`.
2. Найти существующую issue по названию или смыслу.
3. Если issue нет, создать новую на русском.
4. Прочитать актуальный Description, branch/base и ограничения.
5. Перевести issue в "В работе" или ближайший доступный статус.
6. Работать только в активном scope этой issue.

## Corrective iteration

- Продолжать в той же feature-ветке, если актуальный Description не требует другой ветки.
- Делать новый commit; не amend-ить опубликованные commits и не переписывать историю.
- Принятый `Accepted` / `Frozen` scope только проверять на регрессию.
- Если owner feedback добавляет несвязанную область, сначала создать отдельную issue.

## После commit/push

Codex должен добавить комментарий:

- что сделано;
- commit hash;
- какие проверки прошли;
- какие ограничения остались;
- что тестировать Hermes.

После этого feature issue перевести в `Needs Test` или ближайший статус QA. Commit/push не является основанием для `Done`: acceptance даёт owner.

Для UI-задачи в комментарии дополнительно зафиксировать реальный browser click-flow, результат после reload, console/network/HTTP checks и screenshots по scope. Unit tests, mocks, source ordering и прямые JavaScript-вызовы не заменяют browser acceptance. File upload/source selection проверять реальными `filechooser`/file input events с temp fixtures. Computer Use — только optional best-effort diagnostic fallback; он не является обязательным QA/release gate или единственным evidence PASS. Если native OS/runtime не проверялся, написать `not tested` / `owner retest required`.

Перед переводом feature UI-задачи в `Needs Test` обязателен runtime identity gate:

1. Зафиксировать branch и полный final SHA.
2. Запустить свежий QA runtime после checkout этого SHA на отдельном порту.
3. Указать URL, PID, start time и `TEMP`/`REAL` DB/media.
4. Подтвердить identity через startup log, cache key, HTML marker или иной воспроизводимый механизм без UI clutter.
5. Выполнить browser smoke с того же URL, который передаётся Owner.
6. Явно отделить write QA real-data и temp runtime процессами, портами и safety baseline.
7. Оставить QA runtime запущенным для Owner.

Финальный комментарий и отчёт feature UI-задачи обязаны содержать блок `OWNER QA URL`: один точный clickable URL, port, PID, start time, branch, полный SHA, TEMP/REAL DB/media, старые URL/порты, которые нельзя использовать, 3–7 коротких ручных шагов и подтверждение, что runtime оставлен запущенным. Без этого блока UI issue нельзя переводить в `Needs Test`.

## Test tiers и timing

- `T0 Diagnostic`: необходимые команды и один smoke, без product changes, full suite, compileall, Goal Loop и повторного safety audit; 3–10 минут.
- `T1 Merge/docs`: ancestry, local/remote parity, clean tree, `git diff --check` и проверка разрешённого списка файлов; product tests не повторять, Goal Loop не использовать; 3–20 минут.
- `T2 Narrow fix`: focused tests, один узкий browser reproduction, full suite один раз после стабилизации; Goal Loop максимум 2 итерации; 20–45 минут.
- `T3 Cross-flow UI`: focused tests, browser E2E затронутых flows, full suite один раз перед final commit, runtime identity и Owner QA handoff; Goal Loop максимум 3 итерации; 45–90 минут.
- `T4 Data/media`: всё из T3, temp DB/media, destructive/shared-reference tests, failure safety и реальные DB/media hashes; Goal Loop максимум 3 итерации; 60–120+ минут.

Full suite нельзя запускать после каждой Goal Loop iteration. Во время разработки использовать focused checks; full suite запускать один раз после финальной стабилизации, если tier его требует.

В финальном отчёте Codex указывает длительность применимых этапов: investigation, implementation, focused tests, browser E2E, full suite, safety checks, commit/push и runtime handoff; неприменимое отмечает `not run` или `n/a`. Если работа превышает ожидаемый бюджет более чем в 1.5 раза, не расширять scope и не запускать новые широкие проверки: вернуть blocker или конкретное объяснение задержки.

## Hermes QA

Hermes после теста:

- переводит issue в "Готово к релизу", если PASS;
- переводит issue в "QA не пройден" или создаёт bug issue, если FAIL;
- фиксирует конкретный сценарий, фактическое поведение и ожидаемое поведение.

После owner FAIL issue переводится в `Needs Fix`, а Description обновляется до актуального defect scope. Corrective commit не заменяет owner acceptance.

## Bugs

Баги заводить отдельными issue.

Bug issue должна содержать:

- связанный feature/release issue;
- фактический сценарий;
- ожидаемое поведение;
- QA evidence;
- что нельзя трогать.

## Релизы

Merge и release — отдельные issue. Они выполняются только при явном owner authorization в актуальном Description.

Release issue содержит checklist:

- QA PASS;
- version bump;
- release notes;
- package build;
- safety check;
- publish;
- public latest.json;
- Telegram notification;
- owner testing.

Version bump, tag, GitHub Release, `latest.json`, package publication и Telegram не выполнять в feature/bug issue без отдельного разрешения.

После публикации release issue переводить в статус, указанный её Description. Если owner acceptance ещё требуется, использовать `Needs Test`; `Done` ставить только по явному разрешению или подтверждаемому принятому release-процессу.

## Проверка владельцем

После релиза создать или обновить issue:

```text
Проверка владельцем после vX.Y.Z
```

Checklist:

- владелец обновился через кнопку;
- проверил новые функции;
- проверил рабочую запись;
- собраны замечания;
- замечания переведены в Linear issues.

После проверки Сергея связанные задачи можно переводить в "Завершено".

## Правило языка

В Linear писать на русском:

- titles;
- descriptions;
- labels;
- checklist;
- comments.

Английский допустим только для commit hash, URLs, repository names, branch names и технических идентификаторов.
