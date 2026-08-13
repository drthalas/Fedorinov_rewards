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

## Ручное обновление release candidate

- [ ] Используется существующая Desktop-папка `Fedorinov Rewards - Public Current`, а не новая копия.
- [ ] Codex подтвердил `READY FOR OWNER MANUAL UPDATE` только после physical visibility gate.
- [ ] Запустить обычный `start_windows.bat`.
- [ ] Открыть `О программе` и нажать `Проверить обновления`.
- [ ] Проверить показанные current/candidate version; затем Owner самостоятельно решает, нажимать ли `Обновить`.
- [ ] До Owner PASS production `latest.json` остаётся на предыдущей public версии.
