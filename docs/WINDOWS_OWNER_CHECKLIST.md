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

## Physical Owner gate: доступность перед handoff

Полная команда и decision tree находятся в [Windows Portable Preview Runbook](WINDOWS_PREVIEW_RUNBOOK.md#canonical-discovery-physical-windows-test-host).

- [ ] Codex проверил SSH alias `fedorinov-win-gate`.
- [ ] При первом failed probe Codex запустил canonical fallback discovery helper.
- [ ] После discovery Codex повторил SSH через alias, не через старый hardcoded IP.
- [ ] При продолжающемся SSH failure отдельно проверена network reachability актуального resolved address.
- [ ] Один failed ping/IP/SSH probe не использован как доказательство offline state.
- [ ] При неполной или противоречивой диагностике указан статус `connectivity unresolved`.
- [ ] WOL не запускался автоматически.
- [ ] В evidence отсутствуют IP, MAC, host keys, passwords и другие credentials.
