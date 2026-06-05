# История изменений

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
