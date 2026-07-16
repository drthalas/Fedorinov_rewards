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

## Роли, task envelope и остановка

- Owner вручную выбирает модель и reasoning effort в интерфейсе до запуска Codex. Репозиторные инструкции не дают Codex права самостоятельно менять модель.
- ChatGPT-координатор до запускного prompt даёт Owner human-facing рекомендацию: сложность, модель, reasoning effort, test tier, ожидаемое время и stop condition. Это не команда Codex на смену модели.
- Codex выполняет задачу на уже выбранной Owner модели и соблюдает test tier, time budget, stop condition, safety и active scope. Если задача фактически сложнее заявленной, Codex сообщает об этом и останавливается по stop condition.
- Запускной prompt должен быть самодостаточным: branch и base SHA, точные действия, Accepted/Frozen, Out of Scope, required evidence, test tier, time budget и stop condition. Для corrective и сложных UI-багов фразы «прочитай Linear и сделай» недостаточно.

## Corrective iteration и история Git

- Продолжать corrective iteration в той же feature-ветке, если Description не предписывает иначе.
- Создавать новый отдельный commit. Не amend-ить предыдущий опубликованный commit, не rebase-ить и не переписывать историю.
- Commit и push переводят feature-задачу в `Needs Test`, но не в `Done`. Acceptance фиксирует owner.
- Merge в `main` и release выполняются только отдельной контролируемой задачей с явным owner authorization.
- Version bump, tag, GitHub Release, `latest.json`, package publication и Telegram запрещены без отдельного разрешения в текущем Description.

## UI и runtime evidence

- Для локального web UI основной путь — built-in browser / Playwright headed E2E. Unit tests, mocks, source ordering и прямые JavaScript-вызовы не доказывают готовность UI-flow сами по себе.
- Для затронутого UI проверить реальный click-flow, фактический результат после reload, возврат/повторное действие, console/network и application HTTP errors. Screenshots сохранять там, где они нужны для visual evidence.
- File upload/source selection проверять через реальные `filechooser`/file input events и temp fixtures.
- Computer Use — только optional diagnostic fallback: best effort, non-blocking, не единственное доказательство PASS и не QA/release gate.
- Сохранять screenshots или другое evidence, требуемое Description; generated evidence не коммитить, если это явно не разрешено.
- Если native OS, packaged app или embedded runtime недоступны, честно указать `not tested` / `owner retest required`. Не заменять фактический runtime PASS программным вызовом JavaScript.

## Runtime identity и Owner handoff

Перед переводом feature UI-задачи в `Needs Test` Codex обязан:

1. Зафиксировать точный branch и полный commit SHA.
2. Запустить свежий QA runtime после checkout этого SHA на отдельном порту.
3. Указать PID, start time и использование `TEMP` или `REAL` DB/media.
4. Подтвердить runtime identity через startup log, cache key, HTML marker или другой воспроизводимый механизм без UI clutter.
5. Выполнить browser smoke с того же URL, который будет передан Owner.
6. Явно указать старые URL/порты, которые нельзя использовать, и не смешивать write QA real-data и temp runtime без разделения процессов, портов и safety baseline.
7. Оставить QA runtime запущенным для Owner.

Финальный отчёт feature UI-задачи обязан содержать блок `OWNER QA URL`: один точный clickable URL, port, PID, start time, branch, полный SHA, TEMP/REAL DB/media, старые URL/порты, 3–7 ручных шагов и подтверждение, что runtime оставлен запущенным. Без этого блока UI-задачу нельзя переводить в `Needs Test`.

## Test tiers и timing

- `T0 Diagnostic`: необходимые команды и один smoke; без product changes, full suite, compileall, Goal Loop и повторного safety audit; 3–10 минут.
- `T1 Merge/docs`: ancestry/parity/clean tree/`git diff --check` и разрешённый список файлов; product tests не повторять, Goal Loop не использовать; 3–20 минут.
- `T2 Narrow fix`: focused tests, один узкий browser reproduction и full suite один раз после стабилизации; Goal Loop максимум 2 итерации; 20–45 минут.
- `T3 Cross-flow UI`: focused tests, browser E2E затронутых flows, full suite один раз перед commit и runtime handoff; Goal Loop максимум 3 итерации; 45–90 минут.
- `T4 Data/media`: всё из T3, temp DB/media, destructive/shared-reference tests и safety hashes; Goal Loop максимум 3 итерации; 60–120+ минут.

Не запускать full suite после каждой Goal Loop iteration: во время разработки использовать focused checks, а full suite запускать один раз после финальной стабилизации, если его требует tier. В финальном отчёте указывать длительность применимых этапов: investigation, implementation, focused tests, browser E2E, full suite, safety checks, commit/push и runtime handoff; неприменимое отмечать `not run` или `n/a`. При превышении бюджета более чем в 1.5 раза не расширять scope и вернуть blocker либо конкретное объяснение задержки.

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
