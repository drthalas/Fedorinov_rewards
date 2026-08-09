# Windows Portable Preview Runbook

## Что это

Это portable preview web-версии Fedorinov Rewards для первичной проверки на Windows. При открытии `http://127.0.0.1:8080` сразу загружается основной legacy-интерфейс с вкладками старого приложения.

Это не production installer. Архив содержит только код приложения, стартовые скрипты и документацию.

База, фотографии и локальные файлы владельца остаются на компьютере владельца и не входят в архив. Приложение работает локально и не загружает базу или фотографии в облако.

## Что нужно заранее

- Windows 10 или Windows 11.
- Python 3.11 или новее.
- Локальная папка Rewards с данными:
  - `database\MyDatabase.sqlite`
  - `Source\`
  - `SourceMark\`
  - `default\`
  - желательно `default\nofoto.jpg`

При установке Python включите опцию `Add Python to PATH`.

## Запуск

1. Распакуйте архив `FedorinovRewards_WebPreview_v0.1.zip` в отдельную папку.
2. Откройте распакованную папку `FedorinovRewards_WebPreview`.
3. Запустите двойным кликом `start_windows.bat`.
4. При первом запуске будет создан файл `.env` и открыт Notepad.
5. Замените строку:

```text
REWARDS_DATA_DIR=C:\Path\To\Rewards
```

на реальный путь к локальной папке Rewards, например:

```text
REWARDS_DATA_DIR=D:\Rewards
```

6. Сохраните `.env`.
7. Запустите `start_windows.bat` снова.
8. Откройте в браузере:

```text
http://127.0.0.1:8080
```

Скрипт сам создаст `.venv`, установит зависимости и запустит локальный сервер на `127.0.0.1`. Повторный запуск не создаёт второй сервер: уже работающий подтверждённый экземпляр будет переиспользован.

## Остановка

В окне сервера нажмите `Ctrl+C`, подтвердите остановку при запросе и закройте окно.

## Обновление

Кнопка `Обновить` запускает отдельный служебный процесс. Он быстро завершает только подтверждённые процессы Fedorinov Rewards, устанавливает файлы и запускает один backend новой версии. Браузер обновится после проверки версии, PID и папки установки. Закрывать Python через Диспетчер задач или перезагружать Windows не требуется.

При включённом автоматическом перезапуске программа после обновления откроется самостоятельно. Запускайте `start_windows.bat` вручную только как резервный вариант, если приложение не открылось автоматически.

Если порт занят посторонней программой, Fedorinov Rewards покажет ошибку и не будет завершать этот процесс.

## Если порт 8080 занят

1. Откройте `.env`.
2. Измените порт:

```text
APP_PORT=8081
```

3. Запустите `start_windows.bat` снова.
4. Откройте:

```text
http://127.0.0.1:8081
```

## Рабочий preview-режим

По умолчанию preview запускается как рабочий интерфейс с кнопками изменения:

```text
READ_ONLY=false
WRITE_MODE=true
```

Обычное редактирование, загрузка фото и удаления доступны сразу. Удаление остаётся защищено подтверждением и проверкой ссылок. Резервные копии всё равно рекомендуется делать регулярно.

## Режим просмотра

Чтобы выключить редактирование:

1. Откройте `.env`.
2. Укажите:

```text
READ_ONLY=true
WRITE_MODE=false
```

3. Перезапустите `start_windows.bat`.

В режиме просмотра кнопки изменения скрыты или выключены.

## Что не делать

- Не помещать базу и фотографии внутрь папки приложения.
- Не отправлять `.env` в Git или мессенджеры без необходимости.
- Не запускать старые `.exe` из legacy-приложения.
- Не редактировать единственную рабочую базу без backup.
- Не удалять `database`, `Source`, `SourceMark` или `default` из папки Rewards.

## Canonical discovery physical Windows test host

Этот раздел применяется только к выделенному physical Windows release gate. Он не заменяет обычный локальный запуск preview и не требует публиковать адрес, MAC, ключи или credentials.

### Обязательная цепочка

Перед любым выводом `physical Windows offline/unavailable` выполнить шаги по порядку:

1. Проверить канонический SSH alias/hostname:

```bash
ssh -o ConnectTimeout=15 fedorinov-win-gate "cmd.exe /c echo READY"
```

2. Если alias не подключился, запустить существующий fallback discovery helper. Helper проверяет найденный host по закреплённому SSH host key и обновляет machine-local cache актуального адреса:

```bash
resolved_host="$($HOME/.local/bin/fedorinov-win-gate-proxy --discover 22)"
```

3. Не использовать старый hardcoded IP или значение из cache как доказательство. После discovery повторить подключение только через alias:

```bash
ssh -o ConnectTimeout=15 fedorinov-win-gate "cmd.exe /c echo READY"
```

4. Если SSH всё ещё не отвечает, отдельно зафиксировать network reachability актуального найденного адреса, не изменяя конфигурацию host или сети:

```bash
nc -G 3 -z "$resolved_host" 22
```

Проверка актуального адреса допустима только в текущей диагностической сессии. Адрес не коммитить, не помещать в Linear и не превращать в новый hardcoded endpoint.

### Decision tree

| Результат | Вывод | Действие |
| --- | --- | --- |
| Alias подключился | `reachable` | Продолжить gate через `fedorinov-win-gate`. |
| Первый alias probe упал, helper нашёл pinned host, повторный alias подключился | `reachable` | Первый probe считать ложным/устаревшим сигналом. |
| Helper нашёл pinned host и TCP/22 доступен, но SSH session не установилась | `connectivity unresolved` | Зафиксировать конкретный SSH/auth/banner этап; не объявлять host offline. |
| Helper не завершился, resolved address отсутствует или сигналы расходятся | `connectivity unresolved` | Вернуть выполненные шаги и недостающую проверку; не угадывать состояние host. |
| Полная canonical chain завершена и pinned host не найден/не отвечает предусмотренными способами | `probably unavailable` | Сообщить evidence и запросить следующий разрешённый инфраструктурный шаг. Не писать категоричное `offline`, если sleep/power state не доказан отдельно. |

Один failed ping, старый IP, stale ARP/cache, один SSH timeout или неудачный LAN scan не доказывают offline state.

### WOL и изменения сети

- WOL не запускать автоматически после failed probe.
- WOL допустим только когда недоступность или sleep доказаны полной canonical chain, действие предусмотрено текущим runbook и явно разрешено для этого gate.
- Для диагностики не менять power plan, NIC, firewall, router, DHCP, SSH/RDP или другие network/security settings без отдельного scope и разрешения.

### Evidence

В отчёте указывать:

- выполнен ли SSH alias probe;
- запускался ли fallback helper и подтвердил ли pinned host;
- повторялось ли подключение через alias после discovery;
- какая network reachability проверка выполнена;
- итоговый статус: `reachable`, `connectivity unresolved` или `probably unavailable`;
- какие шаги не выполнены и почему.

Не включать в отчёт актуальный IP, MAC, host key, credentials или содержимое machine-local discovery config.
