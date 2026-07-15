# Codex: стартовый файл проекта

Перед любой задачей сначала прочитай:

- `PROJECT_CONTEXT.md`
- `ARCHITECTURE.md`
- `TASKS.md`
- `CHANGELOG.md`
- `DECISIONS.md`
- `QA_NOTES.md`
- `RELEASES.md`
- `LINEAR_PROCESS.md`

## Главные запреты

- Не трогать реальные данные владельца.
- Не изменять `database`, `Source`, `SourceMark`, `default`, `backups`, `data`, реальные фото и документы без явного разрешения.
- Не коммитить `.env`, `.env.daily-report`, `.venv`, logs, updates, archives, generated, dist, ZIP, database, Source, SourceMark, backups, data, фото, PDF, EXE/DLL и токены.
- Не публиковать GitHub Release без явного разрешения.
- Не отправлять Telegram notification без явного разрешения.
- Не запускать real updater apply без явного разрешения.
- Не выводить GitHub token или Telegram token.

## Источники контекста

- Linear = учёт задач, статусов, QA и релизов.
- `docs/context` = постоянная память проекта.
- Git history = факт изменений.
- Hermes QA = подтверждение качества.

Если эти источники расходятся, не угадывай. Сначала сверяй Git, docs и Linear, затем явно фиксируй найденное расхождение.

## Канонический scope Linear-задачи

- Текущий Linear issue Description — единственный канонический активный scope.
- Comments — история задачи, отчёты и evidence. Они не расширяют текущий scope, если Description явно не говорит обратного.
- Разделы `Accepted` / `Frozen` считаются принятыми: не переделывать их, только проверять на регрессию.
- После owner FAIL Description должен быть переписан так, чтобы содержать только актуальный defect scope; принятые части переносятся в `Accepted` / `Frozen`.
- Новые несвязанные требования оформляются отдельной Linear issue, а не добавляются в текущую corrective iteration.

## Corrective iteration и история Git

- Продолжать corrective iteration в той же feature-ветке, если Description не предписывает иначе.
- Создавать новый отдельный commit. Не amend-ить предыдущий опубликованный commit, не rebase-ить и не переписывать историю.
- Commit и push переводят feature-задачу в `Needs Test`, но не в `Done`. Acceptance фиксирует owner.
- Merge в `main` и release выполняются только отдельной контролируемой задачей с явным owner authorization.
- Version bump, tag, GitHub Release, `latest.json`, package publication и Telegram запрещены без отдельного разрешения в текущем Description.

## UI и runtime evidence

- Unit tests и mocks не доказывают готовность UI-flow сами по себе.
- Для затронутого UI проверить реальный visible click-flow, фактический результат, reload, возврат/повторное действие и регрессии соседних сценариев.
- Сохранять screenshots или другое evidence, требуемое Description; generated evidence не коммитить, если это явно не разрешено.
- Если native OS, packaged app или embedded runtime недоступны, честно указать `not tested` / `owner retest required`. Не заменять фактический runtime PASS программным вызовом JavaScript.

## Перед разработкой

1. Перейти в проект:

```sh
cd ~/Projects/Fedorinov_Rewards/Fedorinov_rewards
```

2. Проверить:

```sh
git status --short
git log --oneline -10
```

3. Если working tree грязный и задача не про уже сделанные изменения, остановиться и доложить.
4. Найти или создать Linear issue на русском языке.
5. Прочитать актуальный Description; comments использовать только как историю/evidence.
6. Перевести issue в работу.
7. Проверить объявленные branch, base HEAD, ограничения и `Accepted` / `Frozen` scope.

## После разработки

1. Запустить релевантные проверки.
2. Для UI выполнить фактический browser/runtime flow, а не ограничиваться unit tests/mocks.
3. Commit/push делать только если Description это разрешает.
4. Добавить комментарий в Linear с commit hash, проверками, evidence и ограничениями.
5. После feature commit/push перевести issue в `Needs Test`; `Done` требует owner acceptance или отдельного подтверждаемого основания.
6. Проверить local/remote parity и clean working tree.
7. Не выполнять merge, release или Telegram без отдельного разрешения.

Итоговый отчёт должен содержать:

- branch и initial/final HEAD;
- commit, push и local/remote parity;
- tests и фактический UI/runtime evidence;
- limitations и непроверенные native-сценарии;
- safety hashes, если задача касается данных/media;
- итоговый `git status`.

## Короткий шаблон запуска

```text
Перед началом: прочитай docs/context/CODEX_START_HERE.md

Выполни ALE-XXX строго по актуальному Description в Linear.
Description — единственный канонический активный scope.
Accepted / Frozen не переделывать, только проверить на регрессию.
Комментарии использовать как историю и evidence.
Создать отдельный commit, push и оставить задачу в Needs Test.
Не делать merge или release без явного разрешения owner.
```
