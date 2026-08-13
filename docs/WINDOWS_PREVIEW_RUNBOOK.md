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

### Physical Owner candidate

Постоянная Desktop-папка `Fedorinov Rewards - Public Current` не пересоздаётся для каждого release candidate. До Owner PASS в ней остаётся текущая public production версия и прежние DB/media paths.

После Owner feature PASS, controlled merge/build и минимальных package/parity checks Codex штатным tool `scripts/prepare_owner_candidate_channel.py`:

- размещает exact проверенный ZIP и отдельный `latest.json` в `C:\FedorinovGate\OwnerCandidateChannel`;
- запускает loopback-only channel на `127.0.0.1:18387`;
- изменяет только `UPDATE_MANIFEST_URL` в `.env` постоянного `Public Current`;
- сохраняет canonical production URL для обратимого возврата;
- проверяет в видимом Edge, что `О программе → Проверить обновления` показывает candidate, но не запускает установку.

Production GitHub `latest.json` от этого не меняется, поэтому Сергей candidate не видит. Команды, lifecycle и rollback: `docs/OWNER_CANDIDATE_CHANNEL.md`.

Release stage не повторяет Windows VM updater gate, full suite или product regression без конкретного mismatch либо изменения updater/recovery/packaging/bootstrap/migration. Реальный pre-publication updater gate выполняет Owner из постоянного `Public Current`.

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
