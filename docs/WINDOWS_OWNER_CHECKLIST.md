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

## Проверка release candidate

Эта проверка выполняется до публикации и относится к release-candidate gate.
После Owner PASS exact SHA/version/artifact SHA256 фиксируются. На короткой
publication stage эту Windows-проверку не повторяют без конкретного расхождения.

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

## После публикации

- [ ] Public ZIP и `latest.json` byte/SHA/metadata совпадают с принятым candidate.
- [ ] `Public Current` обновляется только как вспомогательный baseline и не требует второго updater acceptance.
- [ ] Проблема `Public Current` оформляется отдельной infrastructure-задачей и не блокирует безопасную публикацию.
