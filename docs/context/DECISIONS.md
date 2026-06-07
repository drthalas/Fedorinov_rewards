# Принятые решения

## Источники правды

- Linear — учёт задач, статусов, QA и релизных checklist.
- `docs/context` — постоянная память проекта для Codex и Hermes.
- Git history — факт изменений в коде и документации.
- Hermes QA — подтверждение качества перед релизом.
- GitHub Releases — канал доставки owner-сборок и `latest.json`.

Linear важен для процесса, но не является единственным источником правды. Перед работой нужно сверять Linear, `docs/context` и Git history.

## Данные владельца отдельно от приложения

- База, фото и документы владельца не входят в Git и release package.
- Не коммитить `database`, `Source`, `SourceMark`, `default`, реальные фото, PDF, архивы, `.env`, `.env.daily-report`, токены и logs.
- Разработка и QA используют безопасный dev data root:

```text
/Users/hermes/LocalData/FedorinovRewards/Rewards
```

- Не трогать `/Users/hermes/Desktop/Rewards` и другие реальные рабочие копии без отдельного разрешения.

## Рабочий режим записи

После QA приложение должно быть обычной рабочей программой с включённым редактированием:

```text
READ_ONLY=false
WRITE_MODE=true
REQUIRE_BACKUP_BEFORE_WRITE=false
REQUIRE_BACKUP_BEFORE_DANGEROUS_ACTIONS=true
```

Обычные операции доступны без mandatory backup перед каждым сохранением:

- создать или изменить кавалера;
- создать или изменить награду;
- создать или изменить знак;
- изменить справочник;
- добавить, заменить или отвязать фото;
- изменить биографию, комментарии, ссылки, номера и цены.

Опасные действия остаются с подтверждением и защитой:

- delete person;
- delete reward;
- delete mark;
- delete guide item;
- schema migrations;
- restore backup;
- mass operations.

В backlog: убрать пользовательские read-only/write-mode режимы из интерфейса и оставить нормальную рабочую программу.

## Релизы

- Релиз публикуется только после Hermes QA PASS.
- GitHub Release публикуется вручную, не на каждый push.
- `latest.json` — generated release asset, не committed runtime manifest.
- Если release уже существует, assets можно перезаписывать через `gh release upload --clobber` только после отдельного решения.
- Public `latest.json` обязательно проверить перед Telegram notification.
- Telegram notification отправляется только после успешного GitHub Release/latest.json.
- GitHub token и Telegram token не выводить и не коммитить.

## Обновления приложения

- Проверка обновлений идёт через публичный URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

- На стороне владельца GitHub token не нужен.
- Updater сохраняет `.env` и не трогает `database`, `Source`, `SourceMark`, `default`, backups, logs, data и пользовательские файлы.
- Real updater apply не запускать на dev-проекте без отдельного разрешения.
- Автоматический restart после обновления отложен.

## Telegram

- Ежедневные отчёты и релизные уведомления отправляются через существующий colorizer/SAVBot.
- Сергей — основной получатель.
- Александр получает копию.
- Telegram token хранится локально и не должен попадать в Git, docs, logs вывода или Linear.
- Ежедневный отчёт всегда пишется на русском языке: английские commit messages и технические формулировки не отправляются пользователю напрямую.
- Ежедневный отчёт должен быть фактическим: если за день есть реальные commits или задачи, они превращаются в конкретные пользовательские пункты, а не в общие fallback-фразы.

## UI и пользовательские формулировки

- Пользовательские тексты — на русском.
- Не показывать технический мусор владельцу: endpoint, router, repository, commit, hash, internal paths.
- Release notes и Telegram-сообщения должны описывать пользу для владельца, а не внутреннюю реализацию.
