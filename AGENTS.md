# Обязательные инструкции проекта

## Перед началом

1. Всегда сначала прочитать `docs/context/CODEX_START_HERE.md` и указанные там context-файлы.
2. Проверить текущую ветку, `git status --short` и последние commits.
3. Открыть текущую Linear issue и работать только в рамках её актуального Description.

## Модель, бюджет и test tier

- Не пытаться менять модель или reasoning effort в интерфейсе: они выбираются до запуска Owner. Codex выполняет задачу на уже выбранной модели.
- Выполнять test tier, time budget и stop condition из актуального Description или запускного prompt.
- Если фактическая сложность выходит за заявленный бюджет или scope, не расширять работу бесконтрольно: зафиксировать причину и остановиться по stop condition.
- Полные правила постановки задач, test tiers и роли Owner / ChatGPT-координатора / Codex описаны в `docs/context/LINEAR_PROCESS.md`.

## Канонический scope

- Актуальный Linear Description — единственный канонический активный scope задачи.
- Linear comments используются как история, отчёты и evidence, если Description явно не говорит обратного.
- Разделы `Accepted` / `Frozen` не переделывать. Для них разрешены только regression checks.
- После owner FAIL в Description должен остаться только актуальный defect scope, а принятые части должны быть перенесены в `Accepted` / `Frozen`.
- Новую несвязанную область оформлять отдельной Linear issue.

## Git и статусы

- Работать только в ветке, указанной в Description. Не изменять `main` напрямую без явной merge/release-задачи.
- Corrective iteration делать отдельным commit в той же feature-ветке. Не amend-ить и не переписывать опубликованную историю.
- Commit и push не означают `Done`: feature-задачу оставить в `Needs Test`, owner фиксирует acceptance.
- Merge и release являются отдельными контролируемыми шагами и требуют явного owner authorization.
- Не выполнять version bump, tag, release, изменение `latest.json`, package publication или Telegram без отдельного разрешения.

## Проверки и evidence

- Для локального web UI основной путь QA — built-in browser или Playwright headed E2E. UI-задача не считается готовой только по unit tests, mocks, source ordering или прямому вызову JavaScript: нужны реальный click-flow, фактический результат после reload, console/network/HTTP checks и screenshots по scope.
- File upload и source selection проверять реальными `filechooser`/file input events и temp fixtures. Computer Use допустим только как optional, best-effort diagnostic fallback и не является единственным доказательством PASS.
- Если native OS или packaged runtime не проверялись, явно написать `not tested` / `owner retest required`; не заявлять `PASS` по косвенным тестам.
- Destructive/write tests выполнять только на temp DB и temp media. Реальные пользовательские DB, фото и документы не изменять.

## Runtime identity и Owner QA

- Перед переводом feature UI-задачи в `Needs Test` запустить свежий QA runtime после checkout точного final SHA на отдельном порту.
- Зафиксировать branch, полный SHA, URL, PID, start time, тип DB/media (`TEMP` или `REAL`) и runtime identity через startup log, cache key, HTML marker или другой воспроизводимый механизм без UI clutter.
- Выполнить browser smoke с того же URL, который передаётся Owner. Не выдавать long-running или старый runtime за текущую feature-версию.
- Не смешивать write QA real-data и temp runtime без явного разделения процессов, портов и safety baseline. Оставить проверенный QA runtime запущенным для Owner.

## Safety

- Не коммитить secrets, `.env`, `.venv`, реальные DB/media, `Source`, `SourceMark`, `default`, backups, screenshots, Playwright output, logs, temp archives и generated artifacts.
- Не запускать real updater apply и не менять пользовательские данные без отдельного разрешения.
- Не выводить токены и другие credentials в terminal output, документацию или Linear.

## Итоговый отчёт

Указать branch, initial/final HEAD, commit, push и local/remote parity, tests, browser/runtime evidence, limitations, safety hashes и итоговый `git status`. Для UI-задачи дополнительно обязателен блок `OWNER QA URL` с точным URL, портом, PID, start time, branch, полным SHA, типом DB/media, старыми URL/портами, которые нельзя использовать, 3–7 шагами QA и подтверждением, что runtime оставлен запущенным.
