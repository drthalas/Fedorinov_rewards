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
5. Перевести issue в работу.

## После разработки

1. Запустить релевантные проверки.
2. Commit/push делать только если задача это разрешает.
3. Добавить комментарий в Linear с commit hash, проверками и ограничениями.
4. Перевести issue в статус для QA.
5. Не публиковать релиз и не отправлять Telegram без отдельного разрешения.
