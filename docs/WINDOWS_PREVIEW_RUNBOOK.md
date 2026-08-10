# Windows Portable Preview Runbook

## Что это

Это portable preview web-версии Fedorinov Rewards для первичной проверки на Windows. При открытии `http://127.0.0.1:8080` сразу загружается основной legacy-интерфейс с вкладками старого приложения.

Это не production installer. Архив содержит только код приложения, стартовые скрипты и документацию.

База, фотографии и локальные файлы владельца остаются на компьютере владельца и не входят в архив. Приложение работает локально и не загружает базу или фотографии в облако.

Windows VM используется для development/test gate feature-веток по назначенному
tier. После принятого VM gate и physical Owner product PASS полный VM updater
цикл на release stage по умолчанию не повторяется. Exact package, собранный после
merge из `main`, проверяется перед publication на physical Windows по штатному
пути current public -> candidate.

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

Для release gate physical Windows должен начинать с текущей public production
версии и обычного `start_windows.bat`. Проверяются exact artifact SHA, backup,
install, restart, version/runtime identity, сохранность DB/media, один backend и
повторный BAT launch. Forced-failure/rollback требуется, когда release меняет
updater/recovery или Owner явно включил эту проверку в scope.

## Постоянная public baseline на physical Windows

На рабочем столе physical Windows хранится одна постоянная папка:

```text
Fedorinov Rewards - Public Current
```

Она содержит только exact artifact последней опубликованной production-версии,
обычный `start_windows.bat` и `PUBLIC_BASELINE.txt` с version, tag, release commit
и package SHA256. Перед использованием сверить public `latest.json`, GitHub
Release и package SHA, а не полагаться на имя локальной папки.

`.env` подключает существующий внешний Sergey-full data root и отдельную рабочую
state DB. Media и DB не копируются в application folder. `APP_INSTALL_DIR`
оставляется пустым, чтобы штатный launcher определял текущую Desktop-папку, а не
старый task-owned run path.

Правила lifecycle:

1. Candidate всегда разворачивается в отдельной task-owned директории и не
   изменяет public baseline.
2. Папка обновляется только после публикации и проверки exact public artifact.
3. При обновлении нельзя смешивать program files разных версий; сначала
   проверяются version/SHA, затем сохраняются внешние data pointers и обновляется
   marker.
4. После обновления проверить HTTP, `О программе`, runtime identity, один backend
   и повторный `start_windows.bat`.
5. Cleanup удаляет завершённые candidate/runtime paths, но не эту permanent
   папку и не подключённый Sergey-full dataset.

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
- Не использовать `Fedorinov Rewards - Public Current` для feature/candidate QA.
