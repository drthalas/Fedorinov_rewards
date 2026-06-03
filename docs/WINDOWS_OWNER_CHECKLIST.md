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
- [ ] Backup сделан перед любыми write-тестами.
- [ ] Backup location: ______________________________
- [ ] Backup проверен и читается.

## Режим запуска

- [ ] Read-only preview: `READ_ONLY=true`, `WRITE_MODE=false`.
- [ ] Write test only after backup: `READ_ONLY=false`, `WRITE_MODE=true`.
- [ ] После write-теста режим возвращен в read-only.

## Проверка preview

- [ ] `start_windows.bat` запускается.
- [ ] Открывается `http://127.0.0.1:8080`.
- [ ] Dashboard открывается.
- [ ] Persons открывается.
- [ ] Rewards открываются.
- [ ] Marks открываются.
- [ ] Guides открывается.
- [ ] Search открывается.
- [ ] Фотографии отображаются или показывается понятный placeholder.
