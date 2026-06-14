# История изменений

## v0.1.9

Статус: выпущено.

Дата релиза: 2026-06-14.

Ключевые изменения:

- Патч-релиз после проверки владельцем v0.1.8, включающий исправления ALE-197.
- Восстановлена обычная листалка всех фото кавалера.
- Все безопасные фото из папки кавалера входят в обычный slideshow карточки.
- Дополнительные фото можно листать сразу из карточки, без обязательного нажатия "Показать все фото".
- Lightbox убирает дубли фото, absolute paths в UI не раскрываются.
- Unsafe files не добавляются в просмотр фотографий.
- Карточка кавалера заметно уплотнена: добавлены viewport-limit и внутренние scroll-блоки.
- Фото больше не раздувают карточку, horizontal overflow не обнаружен.

Проверки перед релизом:

- Unit tests: 284 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Smoke: PASS.
- Package SHA256 фиксируется в `latest.json`, GitHub Release и финальном отчёте после сборки.

Ключевой commit:

- `5f0e639` Fix slideshow all photos and compact person card.

## v0.1.8

Статус: выпущено.

Дата релиза: 2026-06-14.

Ключевые изменения:

- Стабильный релиз после дополнительной проверки владельца, включающий исправления ALE-195 поверх v0.1.7.
- Уплотнена карточка кавалера, открываемая после double click из вкладки "Награды".
- Slideshow карточки кавалера дополняется безопасными фото из каталога кавалера.
- Дубли фото в slideshow убираются, absolute paths в UI не раскрываются.
- CSV больше не выводит boolean как `true/false`: теперь используется `1/0`.
- CSV остаётся Excel-friendly: UTF-8 BOM и разделитель `;`.
- Save As честно объясняет ограничение браузера: web-страница не получает путь выбранной пользователем папки и не может открыть её автоматически.
- В "Сводной таблице" добавлен resize колонок и строк.
- В "Поиске" мини-фото масштабируются при изменении ширины колонок и высоты строк.
- Lightbox после resize работает.

Проверки перед релизом:

- Unit tests: 283 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Browser smoke: PASS.
- Package SHA256 фиксируется в `latest.json`, GitHub Release и финальном отчёте после сборки.

Ключевой commit:

- `9ecf37f` Fix owner feedback after v0.1.7 check.

## v0.1.7

Статус: выпущено.

Дата релиза: 2026-06-12.

Ключевые изменения:

- Стабильный релиз после проверки владельца, объединяющий исправления v0.1.5, v0.1.6 и ALE-192.
- Быстрый поиск ФИО на вкладке "Награды" переведён в явное поле "Быстрый поиск по ФИО".
- Enter открывает первое совпадение в списке кавалеров.
- Список кавалеров больше не автофокусится после загрузки страницы и не выглядит основным сценарием поиска.
- Компактные мини-фото в поиске из v0.1.6 сохранены: frame 44x44 px, изображение до 40x40 px, placeholder того же размера.
- Resize-ручки колонок и строк в поиске стали заметнее.
- Save As честно объясняет ограничение браузера: веб-страница не может автоматически открыть локальную папку.
- Fallback download и "Открыть копию файла" сохранены.

Проверки перед релизом:

- Unit tests: 282 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Browser smoke: PASS.

Ключевые commits:

- `37003cd` Fix search photo thumbnails.
- `0e16915` Fix owner feedback after v0.1.5 check.

## v0.1.6

Статус: выпущено.

Ключевые изменения:

- Исправлен режим "мини-фото" во вкладке "Поиск".
- Фотографии в таблице теперь показываются компактными превью и не раздувают строки.
- Placeholder для отсутствующих фото отображается в такой же рамке.
- Полное фото открывается по клику в существующем просмотрщике.
- Lightbox/zoom, изменение размеров таблицы и CSV остались рабочими.
- Windows native Save As через отдельную Windows VM остаётся отложенной проверкой владельца.

Ключевой commit:

- `37003cd` Fix search photo thumbnails.

## v0.1.5

Статус: выпущено.

Release URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/tag/v0.1.5
```

Ключевые изменения:

- CSV-файлы открываются в Excel корректно по колонкам.
- Исправлен layout карточки кавалера: ФИО, звание, дата и ссылки больше не схлопываются в узкие колонки.
- Исправлен Save As для PDF-буклета и fallback обычной загрузки.
- Справочник "Звания / специальности" сортируется по алфавиту.
- Во вкладке "О программе" отображается дата версии, название программы можно редактировать и сохранять.
- На вкладке "Награды" добавлена клавиатурная навигация по списку кавалеров и быстрый поиск по первым буквам ФИО.
- Краткая биография сохраняется и отображается после перезагрузки.
- Форма редактирования кавалера стала компактнее.
- Во вкладке "Поиск" добавлен режим мини-фото вместо признаков `0/1`.
- Мини-фото открываются в существующем просмотрщике с zoom/lightbox.
- Таблица поиска получила изменение ширины колонок и высоты строк.
- При поиске по наименованию награды добавлены колонки фото наградной книжки, сторона 1/2.
- Windows native Save As через отдельную Windows VM отложен владельцем и не блокирует релиз.

Ключевые commits:

- `2aab244` Fix Excel CSV and person card layout.
- `f48fc43` Fix booklet PDF Save As gesture handling.
- `ab1e88b` Fix Save As fallback download.
- `f07a0a1` Improve ranks directory and about settings.
- `06a6e25` Add keyboard navigation and typeahead for rewards list.
- `04fa030` Fix biography saving and edit form UX.
- `2b41a0c` Add search photo mode and resizable table.
- `6ce6f1c` Prepare v0.1.5 release.

## v0.1.4

Статус: выпущено.

Release URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/tag/v0.1.4
```

Ключевые изменения:

- Исправлен главный экран "Награды": выбранный кавалер остаётся видимым в левом списке.
- Добавлено дополнительное подтверждение удаления кавалера.
- Закреплена строка итогов внизу рабочей области.
- Форма редактирования кавалера стала компактнее: фотографии доступны в первом экране.
- Исправлены сохранение и отображение краткой биографии.
- Сводная таблица получила каскадные фильтры и сортировку шахматки по столбцам.
- CSV получил понятную подсказку после сохранения.
- Поиск получил поиск по номеру награды и сортировку результатов.
- В поиск и CSV добавлены признаки фото и документов по наградам.
- Фото, вставленные из буфера обмена, сохраняются в JPEG.

Ключевые commits:

- `2dcc038` Polish owner feedback rewards screen.
- `d2e1d7f` Improve summary filters and sorting.
- `6d9c44b` Improve search award results.
- `1eb4621` Save pasted photos as JPEG.
- `a2bd6f6` Fix owner feedback layout blockers.

## v0.1.3

Статус: выпущено.

Release URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/tag/v0.1.3
```

Ключевые изменения:

- Исправлены фото-фреймы: реальные фото и блоки "Нет фото" теперь находятся в одинаковых серых рамках.
- Фото внутри рамки центрируется, сохраняет пропорции и не растягивается.
- Добавлен PDF-экспорт сводной таблицы.
- Добавлен PDF-экспорт режима "Шахматка по кавалерам".
- PDF учитывает выбранные фильтры.
- Если таблица слишком широкая для PDF, программа показывает понятное сообщение и предлагает использовать фильтры или CSV.

Ключевые commits:

- `db2d5c5` Fix legacy photo frame layout.
- `7b2eadd` Add summary PDF export.

## v0.1.2

Статус: выпущено.

Release URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/tag/v0.1.2
```

Ключевые изменения:

- Сводная таблица-шахматка по кавалерам и наградам.
- CSV-выгрузка шахматки для Excel.
- Открытие каталога кавалера.
- Архивирование материалов кавалера.
- Системный выбор места сохранения для архива, PDF-буклета и CSV.
- Улучшенный просмотр фото: zoom, pan, reset.
- Вставка фото из буфера обмена.
- PDF-буклет кавалера.
- Рабочий режим записи.
- Удаления больше не требуют mandatory backup при `REQUIRE_BACKUP_BEFORE_WRITE=false`, но требуют подтверждения.
- Каскадные справочники: страна -> категория -> подкатегория -> наименование.
- Обязательные поля для кавалера, награды и знака.
- Поиск с пользовательскими колонками, подсказками из базы и возвратом к результатам.
- Финальная полировка форм: русские ошибки, сохранение введённых значений после validation error.
- Браузерный Save As для архива кавалера, PDF-буклета и CSV; Windows Chrome/Edge native dialog оставлен отдельным пунктом owner QA.
- Главный экран "Награды": сортировка кавалеров, быстрый поиск, внутренний скролл перечня наград, одинаковые фото-карточки.
- Улучшенный поток добавления кавалера: после создания открывается дозаполнение фото и документов.
- Улучшенный поток добавления награды: после создания открывается редактирование фото и документов награды.
- Карточка кавалера и legacy-панель лучше переносят длинные ФИО, ссылки, биографию и комментарии.

Ключевые commits:

- `b4f50f4` Add summary matrix by persons and rewards.
- `8969425` Add person folder archive and photo viewer controls.
- `61fa437` Add save dialogs for archive PDF and CSV.
- `f63a3e1` Add person booklet PDF.
- `a364e93` Fix delete backup guard in working write mode.
- `0ddd6fc` Add cascading guides and required fields.
- `07e8f54` Improve search results and suggestions.
- `790744e` Polish forms validation and errors.
- `b1b9fbc` Fix cascading guide dropdowns.
- `6920b81` Prepare v0.1.2 release.
- `b1e69e3` Implement browser Save As for exports.
- `2d48ae0` Polish rewards screen layout.
- `aaed551` Improve person creation flow.
- `c0f9e04` Improve reward creation flow.
- `b4b4d2f` Polish person card layout.

## v0.1.1

Статус: выпущено.

Ключевые изменения:

- Видимый статус процесса обновления после нажатия "Обновить".
- Защита от повторного запуска обновления.
- Фильтры на главном экране "Награды".
- Итоги на главном экране.
- Двойной клик по кавалеру.
- Кликабельные безопасные ссылки.
- Escape как "Вернуться" на формах.
- Поиск с пустым запросом по выбранной категории.
- Контекстные переходы в справочники из форм.
- Исправлен возврат из карточки кавалера обратно в legacy rewards.
- Telegram-уведомления о релизах через colorizer/SAVBot.

Ключевые commits:

- `1944c9a` Add update progress UI and release notifications for v0.1.1.
- `3aab9a0` Improve legacy rewards filters and totals.
- `41e71b4` Improve search UX and contextual guides.
- `750c1ad` Fix person detail return to legacy.
- `8a8b53b` Improve v0.1.1 release notes and resend notification.

## v0.1.0

Статус: выпущено.

Ключевые изменения:

- Первая Windows portable preview-сборка.
- Основной legacy-интерфейс как стартовый экран.
- Фото открываются крупно на странице.
- CRUD для кавалеров, наград, знаков и справочников.
- Краткая биография.
- Базовая сводная таблица и CSV.
- Публичная проверка обновлений через GitHub Release `latest.json`.
- Manual GitHub Actions workflow для релизов.

Ключевые commits:

- `87aa209` Make legacy UI primary and fix return navigation.
- `f84cae7` Make legacy UI single shell and add photo lightbox.
- `92ff53d` Stage 3F photo viewer and photo management.
- `fa80012` Stage 3H guides CRUD.
- `f961593` Stage 3I form parity and biography.
- `a978f32` Stage 3J summary table and CSV export.
- `eecb529` Add public GitHub update checker.
- `34adc42` Add GitHub release package publishing.
- `2447fd6` Add manual GitHub release workflow.

## Постоянные процессы

- Ежедневные Telegram-отчёты: `d95bb8d`, `c801851`, `5bf0a41`.
- One-click updater: `ee087d8`.
- GitHub release package publishing: `34adc42`, `2447fd6`.
- Release notification correction mode: `8a8b53b`.
