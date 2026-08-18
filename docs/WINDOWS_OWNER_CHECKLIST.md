# Windows Owner Preview Checklist

## Компьютер

- [ ] Windows version: ______________________________
- [ ] Python 3.11+ установлен.
- [ ] При установке Python была включена опция `Add Python to PATH`.

## Локальная папка Rewards

- [ ] Путь к папке Rewards: ______________________________
- [ ] Есть `database\MyDatabase.sqlite`.
- [ ] Есть папка `Source\`.
- [ ] Есть папка `SourceMark\`.
- [ ] Есть папка `default\`.
- [ ] Есть `default\nofoto.jpg`.

## Безопасность данных

- [ ] База и фотографии находятся вне папки приложения.
- [ ] При необходимости есть отдельная резервная копия данных.

## Режим запуска

- [ ] Read-only preview: `READ_ONLY=true`, `WRITE_MODE=false`.
- [ ] Рабочий режим: `READ_ONLY=false`, `WRITE_MODE=true`.

## Проверка preview

- [ ] `start_windows.bat` запускается.
- [ ] Повторный запуск `start_windows.bat` не создаёт второй backend.
- [ ] Открывается `http://127.0.0.1:8080`.
- [ ] Dashboard открывается.
- [ ] Persons открывается.
- [ ] Rewards открываются.
- [ ] Marks открываются.
- [ ] Guides открывается.
- [ ] Search открывается.
- [ ] Фотографии отображаются или показывается понятный placeholder.
- [ ] После обновления приложение перезапускается само и показывает новую версию.
- [ ] Перед release проверены PID, install root и версия через локальный runtime identity.

## Permanent Owner candidate channel

One-time bootstrap выполняется только по отдельному Owner-разрешению:

- [ ] Candidate собран из exact accepted feature/release HEAD; до этой ручной проверки `main` не менялся.
- [ ] Сохранён backup `.env` permanent `Public Current`.
- [ ] `UPDATE_MANIFEST_URL` указывает на `http://Mac-mini-hermes.local:18387/latest.json`.
- [ ] В «О программе» Owner вручную запускает проверку и видит exact candidate version.
- [ ] Owner сам выполняет updater/product acceptance и явно сообщает PASS или FAIL.
- [ ] Merge в `main` и production publication не начинаются без Owner PASS и отдельного разрешения.
- [ ] Codex не подключался к physical Windows на release-candidate stage.
- [ ] Production channel Сергея остаётся публичным GitHub `latest.json`.

Полная процедура и rollback: `docs/OWNER_CANDIDATE_CHANNEL.md`.
