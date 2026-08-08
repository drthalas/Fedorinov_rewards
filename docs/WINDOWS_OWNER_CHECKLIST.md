# Windows Owner Preview Checklist

## Роль physical Windows

Этот чек-лист предназначен для ручной Owner acceptance на physical Windows. Windows VM — технический контур Codex и не заменяет эту приёмку для product UI/UX, performance/scale и release user-flow задач. Перед handoff Codex передаёт один exact candidate: SHA, PID, port и local URL; Owner не должен искать preview по старым портам или запускать несколько runtime.

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

## После проверки

- [ ] Owner сообщил явный PASS или FAIL для переданного candidate.
- [ ] Codex остановил candidate при следующем Test Environment Cleanup, если он больше не нужен.
