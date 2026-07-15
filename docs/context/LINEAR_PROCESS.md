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

Для UI-задачи в комментарии дополнительно зафиксировать реальный visible click-flow, результат, reload/regression evidence и screenshots по scope. Если native OS/runtime не проверялся, написать `not tested` / `owner retest required`.

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
