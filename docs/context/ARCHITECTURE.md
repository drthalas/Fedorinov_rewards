# Архитектура

## Общая схема

Приложение — локальный FastAPI backend с Jinja2 templates и статикой. Основной пользовательский интерфейс — legacy-like web shell:

```text
/legacy?tab=rewards
```

Standalone routes остаются для карточек, форм, печатных страниц, CSV и технических сценариев.

## Основные папки

- `backend/app/routers` — HTTP routes.
- `backend/app/services` — бизнес-логика, безопасность, media, updater, archive, booklet.
- `backend/app/repositories` — чтение и запись SQLite.
- `backend/app/templates` — Jinja2 templates.
- `backend/app/static` — CSS и frontend JavaScript.
- `scripts` — диагностика, сборка package, релизы, Telegram, update helpers.
- `release_notes` — human-readable notes для release package и Telegram.
- `docs/context` — постоянная память проекта.

## Routers

Ключевые области:

- legacy shell и вкладки;
- persons;
- rewards;
- marks;
- guides;
- search;
- summary / summary matrix CSV;
- media;
- photos upload/unlink;
- updates check/apply/status.

## Services

Важные services:

- media resolver: безопасно отдаёт фото только из `REWARDS_DATA_DIR`;
- photo upload/unlink: пишет через guarded pipeline, не удаляет физические фото при отвязке;
- guides: справочники званий и дерево наград/знаков;
- navigation: безопасный `return_to`;
- update checker/updater: public latest.json, SHA256, package validation, backup app files;
- person files: открыть каталог кавалера и архивировать материалы;
- save dialog: системный выбор места сохранения для архива, PDF и CSV;
- booklets: подготовка printable HTML и PDF-буклета;
- release notification: генерация Telegram-сообщений о релизе.

## Repositories

SQLite queries должны быть параметризованы. Пользовательский ввод не вставлять в SQL строковой конкатенацией.

Репозитории читают и пишут таблицы:

- `person`;
- `rewards`;
- `mark`;
- `guide`;
- `guide_lev_0` ... `guide_lev_4`.

## Legacy UI

Основные вкладки:

- "Награды";
- "Поиск";
- "Знаки";
- "Свод.таблица";
- "О программе".

Главный экран "Награды" содержит список кавалеров, фильтры, награды выбранного кавалера, итоги, фото, ссылки и действия.

## Справочники

Используется дерево:

```text
guide_lev_0 -> guide_lev_1 -> guide_lev_2 -> guide_lev_3 -> guide_lev_4
```

В формах наград и знаков работает каскад:

```text
страна -> категория -> подкатегория -> наименование
```

Edit-формы должны preselect текущие ids и не затирать их при сохранении.

## Поиск

Поиск работает по scope:

- persons;
- rewards;
- marks;
- all.

Подсказки берутся из базы, browser autocomplete старой истории выключен. Переходы из поиска передают safe `return_to` обратно к результатам.

## Сводная таблица

Есть два режима:

- "Шахматка по кавалерам" — основной режим;
- "Свод по наградам" — агрегированный режим.

Шахматка показывает кавалеров строками, награды колонками, значения `0`, `1` или количество. CSV шахматки выгружается для Excel.

## Фото

Фото открываются в lightbox. Есть zoom, pan, reset, wheel zoom, next/prev и Escape close. Clipboard paste работает через browser Clipboard API, если браузер поддерживает чтение изображений из буфера.

## Каталог и архивирование

Кнопка "Открыть каталог" открывает только безопасный каталог кавалера внутри `REWARDS_DATA_DIR`.

Кнопка "Архивировать" архивирует только каталог конкретного кавалера. Исходные файлы не удаляются. Архив сохраняется через системный выбор места или безопасный fallback.

## Браузерный Save As

Основной путь сохранения архива, PDF и CSV использует File System Access API: браузер открывает системное окно выбора файла через `showSaveFilePicker`.

Если браузер не поддерживает этот API или окно выбора файла не удалось открыть, приложение использует fallback обычной загрузки: получает файл как Blob и запускает временную ссылку `download`. Отмена пользователем в системном окне не запускает fallback автоматически.

Windows Chrome/Edge проверяются отдельно во время QA владельца. Если Windows VM недоступна, кодовый fallback всё равно должен проверяться автоматизированно или через эмуляцию отсутствия `showSaveFilePicker`.

## PDF-буклет

`/persons/{id}/booklet` показывает printable HTML preview.

`POST /persons/{id}/booklet.pdf` генерирует PDF через reportlab, если библиотека доступна. Generated PDF не должен попадать в Git.

## Release package

`scripts/build_release_package.py` собирает versioned Windows ZIP и `dist/latest.json`.

`scripts/check_package_safety.py` проверяет, что в package не попали данные, фото, базы, `.env`, бинарники, вложенные ZIP и другие запрещённые файлы.

GitHub Release содержит:

- `FedorinovRewards_WebPreview_vX.Y.Z.zip`;
- `latest.json`.
