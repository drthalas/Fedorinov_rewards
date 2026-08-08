# Релизы

## Общий процесс

1. Убедиться, что Hermes QA PASS.
2. Поднять `APP_VERSION` в `backend/app/version.py`.
3. Создать или обновить `release_notes/X.Y.Z.md`.
4. Обновить docs/context при необходимости.
5. Запустить локальные проверки.
6. Собрать release package:

```sh
python3 scripts/build_release_package.py
```

7. Проверить safety:

```sh
python3 scripts/check_package_safety.py dist/FedorinovRewards_WebPreview_vX.Y.Z.zip
```

8. Выполнить publish dry-run:

```sh
python3 scripts/publish_github_release.py --dry-run
```

9. Опубликовать через Manual Release workflow или обновить существующие assets, если это явно разрешено.
10. Проверить public `latest.json`:

```sh
curl -fsS -L https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

11. Только после успешного public `latest.json` отправить Telegram notification.
12. Обновить Linear release issue.
13. Перевести owner testing issue в проверку владельцем.

## Если release уже существует

По умолчанию не перезаписывать.

Если дано отдельное решение обновить assets существующего release:

```sh
gh release upload vX.Y.Z \
  dist/FedorinovRewards_WebPreview_vX.Y.Z.zip \
  dist/latest.json \
  --repo drthalas/Fedorinov_rewards \
  --clobber
```

После `--clobber` обязательно проверить public `latest.json`.

## Telegram notification

Каноническая пользовательская инструкция генерируется
`scripts/generate_release_telegram_message.py`. После обновления основной
сценарий — автоматический перезапуск приложения. Ручной запуск
`start_windows.bat` допустим только как fallback, если приложение не открылось
самостоятельно. Не добавлять обязательный повторный запуск BAT в release notes,
dry-run или финальное сообщение.

Сначала dry-run:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --dry-run
```

Если текст корректный:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --send
```

Не отправлять Telegram, если release/latest.json не проверены.

## v2.0.10

Статус: release candidate, не опубликован.

Дата подготовки: 2026-08-07.

Тип: integrated UI and workflow patch.

Состав:

- Компактная алфавитная навигация внутри списка кавалеров с сохранением поиска, выбора и повторных переходов.
- Post-create flow: новый кавалер остаётся открыт, доступны фотографии и последовательное добавление наград до финального сохранения.
- Результаты поиска наград содержат фотографию кавалера; пустое состояние знаков использует штатную тёмную тему.
- Post-create ссылки и блок наград выровнены без изменения функций медиа и наград.
- Сохранены оптимизации записи, безопасный managed-media lifecycle, корректная сортировка и непрерывные переходы без чёрных кадров.

Release gate:

- Candidate package и manifest изолируются от production update channel.
- Обязателен полный Tier 4 updater gate с exact public `v2.0.9` на Windows VM через штатный `start_windows.bat` и UI updater на постоянном mutable Sergey fixture.
- Production publication, `latest.json` и Telegram разрешены только после отдельного physical Owner PASS.

## v2.0.9

Статус: выпущено.

Дата релиза: 2026-08-04.

Тип: performance and transition patch.

Состав:

- Ускоренная запись кавалеров и managed media с сохранением atomicity, rollback и shared-media safety.
- Немедленная обратная связь при сохранении и удалении и защита от повторного submit.
- Непрерывный render lifecycle без пустого или чёрного промежуточного экрана.
- Автоматический выбор и прокрутка нового кавалера после сортировки списка.
- Стабильные выделение, прокрутка, фильтры и сортировка при переходах.
- Быстрая готовность вкладки «Кавалеры» на full dataset без лишнего синхронного layout при нулевой позиции списка.

Release gate:

- Candidate package и manifest изолируются от production update channel.
- Обязательны три независимых updater cycle с exact post-recovery public `v2.0.7` на Windows VM и постоянном mutable Sergey fixture без per-cycle DB/media copy/reset.
- Production publication, `latest.json` и Telegram разрешены только после отдельного physical Owner PASS.

## v2.0.7

Статус: выпущено.

Дата релиза: 2026-07-22.

Тип: corrective recovery patch.

Состав:

- Исправлен запуск recovery-архива в стандартном Windows `cmd.exe`.
- Пользовательский BAT сведён к короткому ASCII-only bootstrap с Windows CRLF; основная логика восстановления выполняется app-owned helper.
- Сохранены явный выбор установки, проверенный backup, rollback и защита DB/media.
- Recovery поддерживает восстановление установок `v2.0.5` и `v2.0.6` без ручного переноса данных.
- Предыдущий recovery-архив `v2.0.6` не заменяется; исправление публикуется отдельным immutable release.

Проверки:

- Exact public `v2.0.6` recovery failure воспроизведён на native Windows `cmd.exe`.
- Native Windows parser/path/codepage gate, target selection, backup/install/rollback и повторный штатный запуск: PASS.
- Exact public `v2.0.5` transition и corrective recovery на TEMP installations: PASS.
- Full suite, compileall, JS syntax, package safety и packaged Browser smoke: PASS.
- Реальные Owner/development DB и media не изменялись.

## v2.0.6

Статус: выпущено.

Дата релиза: 2026-07-22.

Тип: production recovery patch.

Состав:

- Исправлен постоянный Windows startup timeout после `v2.0.5`.
- Сохранена строгая runtime identity и single-instance проверка; active startup progress и no-progress timeout разделены.
- Повторный запуск использует безопасный build-scoped pycache вне install tree.
- Диагностика отличает slow start, crash, bind failure, registry mismatch и HTTP identity mismatch.
- Runtime server принимает как новый явный startup-path, так и точный legacy argv публичного updater `v2.0.5`.
- Для нерабочей `v2.0.5` применяется отдельный recovery ZIP с подтверждением выбранной установки, проверенным backup и автоматическим сохранением DB/media.

Проверки:

- Focused Windows startup/handoff/rollback/single-instance/unrelated-port regression: PASS.
- ALE-317 regressions, full suite, compileall и JS syntax: PASS.
- Exact public `v2.0.5` updater, recovery package, TEMP packaged Browser smoke и package safety: PASS.
- Реальные Owner/development DB и media не изменялись.

## v2.0.5

Статус: выпущено.

Дата релиза: 2026-07-22.

Тип: patch release.

Состав:

- Более предсказуемое создание и редактирование кавалеров и наград.
- Строгая проверка четырёхзначного года рождения и корректная проверка номера награды.
- Отключённые browser autocomplete-подсказки в рабочих формах.
- Сохранённые улучшения фотографий, каталога и производительности на больших базах.
- Надёжный single-instance handoff при обновлении: старый backend останавливается, затем запускается единственный backend новой версии.
- Закреплённый dependency graph для воспроизводимой установки и обновления.

Проверки:

- Focused form/updater/runtime regression, full suite, compileall и JS syntax: PASS.
- TEMP packaged Browser smoke, package safety и updater compatibility: PASS.
- Реальные DB и media не изменялись.

## v2.0.4

Статус: выпущено.

Дата релиза: 2026-07-20.

Тип: patch release.

Состав:

- Более быстрые и стабильные карточки и основные экраны на больших базах.
- Значительно ускоренный «Справочник» без destructive-расчётов при обычном просмотре.
- Проверка удаления только после явного нажатия «Удалить» с сохранёнными точными сведениями и защитой общих файлов.
- Более отзывчивая кнопка `+` для вставки из буфера или выбора файла.
- Полностью закреплённый набор зависимостей для воспроизводимой установки и обновления.

Проверки:

- Focused regression, full suite, clean pinned install и TEMP Browser smoke: PASS.
- Package safety, legacy updater compatibility, TEMP backup/install/restart/update-check/rollback: PASS.
- Реальные DB/media SHA и fingerprints до/после релизной процедуры совпадают.

## v2.0.3

Статус: выпущено.

Дата релиза: 2026-07-18.

Тип: patch hotfix.

Состав:

- Восстановленный packaged background пустого экрана «Кавалеры» с updater-compatible optimized artwork.
- Ускоренное открытие карточек кавалеров на больших базах без eager destructive preview.
- Lazy delete confirmation с точными counts и сохранённой безопасностью общих media.
- Конечный frontend timeout, гарантированная очистка loading state и повторяемый запрос после ошибки.

Проверки:

- Owner/manual QA ALE-300: PASS.
- Focused regression и full suite: PASS.
- Packaged CSSOM/background, TEMP browser smoke и performance budgets: PASS.
- v0.1.14 updater compatibility, backup/install/restart/update-check/rollback: PASS.
- Real DB/media SHA и fingerprint до/после релизной процедуры совпадают.

## v2.0.2

Статус: выпущено.

Дата релиза: 2026-07-18.

Тип: patch release.

Состав:

- Безопасный lifecycle замены и удаления managed media с reference-counted cleanup общих файлов.
- Полное удаление кавалеров, наград, знаков, званий и элементов справочника с owned row/file/folder cleanup, quarantine/recovery и safe blocking.
- Корректный возврат в исходный legacy context после удаления.
- Единые transient notifications и очистка одноразовых query markers.
- Подтверждение перед заменой занятого image slot.
- Consume-once поведение clipboard image с обычным file picker для уже использованного содержимого.
- Финальная фотография empty state вкладки «Кавалеры».

Проверки:

- Owner/manual QA: PASS.
- Full suite, focused lifecycle tests и browser smoke: PASS.
- Старый публичный updater принимает пакет с новым фоном; system UI assets встроены в packaged CSS.
- Temp backup/install/restart/update-check/rollback: PASS.
- Real DB/media SHA и fingerprint до/после релизной процедуры совпадают.

## v2.0.1

Статус: выпущено.

Дата релиза: 2026-07-12.

Тип: updater compatibility hotfix.

Состав:

- Совместимый one-click upgrade path из публичной v0.1.14 в полный v2-дизайн.
- Системные bitmap-assets встроены в packaged CSS и не являются запрещёнными ZIP entries для старого updater.
- Новый updater использует общий producer/consumer archive policy и сохраняет точечную защиту системных UI-assets.
- Повтор после ошибки v2.0.0 использует новую metadata, versioned URL, checksum и отдельное имя ZIP.

Проверки:

- Фактический updater-код tag v0.1.14 принимает v2.0.1 package: PASS.
- Temp E2E backup/install/restart-check/rollback: PASS.
- Full suite, package safety, browser smoke и public assets проверяются до Telegram notification.
- Real DB/media SHA и fingerprint до/после релизной процедуры должны совпадать.

## v2.0.0

Статус: выпущено.

Дата релиза: 2026-07-12.

Тип: major release.

Состав:

- Полный визуальный редизайн приложения в тёмном архивно-военном стиле.
- Новый главный экран «Кавалеры» и полностью переработанный «Справочник».
- Обновлённые карточки кавалеров и наград, формы и управление фотографиями.
- Единый shell/header и обновлённые «Поиск», «Знаки», «Сводная таблица» и «О программе».
- Исправления clipping, scroll, ссылок, подписей, dropdown/list UX и состояний дерева.

Проверки:

- Owner/manual QA: PASS.
- Unit tests: 377 PASS.
- Browser smoke и temp write-smoke: PASS.
- Data baseline: person 108, rewards 351, mark 146, guide 18.
- Media baseline: total 961, existing 950, missing 11.
- Real DB/media SHA и fingerprint до/после релизной процедуры совпадают.
- Public `latest.json` проверяется до Telegram notification.

## v0.1.14

Статус: выпущено.

Дата релиза: 2026-07-10.

Тип: patch release.

Состав:

- Включает owner-approved ALE-232, ALE-233, ALE-234, ALE-235, ALE-236, ALE-238, ALE-239, ALE-240, ALE-241, ALE-243, ALE-244 и ALE-245.
- Безопасное удаление, проверка дублей, единая навигация, экран "Кавалеры", год рождения и действия наград.
- Справочник: ручной рейтинг и изображения, сохранение дерева, live-preview и корректное сворачивание.
- Реальные данные не изменялись; автоматический импорт рейтинга и загрузка изображений из интернета не выполнялись.

Проверки:

- Owner/manual QA PASS.
- Unit tests: 346 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline и SHA256 фиксируются в GitHub Release и финальном отчёте.
- Public verification перед Telegram обязательна.

## v0.1.13

Статус: выпущено.

Дата релиза: 2026-07-09.

Тип: patch release.

Состав:

- Включает стабильную базу v0.1.12.
- Включает ALE-232: безопасное удаление награды с подтверждением; cancel/dismiss confirm не отправляет POST и не удаляет запись.
- Включает ALE-233: проверка дублей наград по всей базе по связке "наименование + номер"; пустой номер разрешён, добавлена интерактивная подсветка номера.
- Включает ALE-234: понятная навигация и заголовки наград; safe `return_to`, external `return_to` блокируется.
- Включает ALE-235: исправлен скролл "Перечень наград".
- Включает ALE-236: read-only аудит кнопок возврата.
- Включает ALE-238: detail-view награды показывает название и одну кнопку "Назад".
- Включает ALE-239: единая верхняя пользовательская навигация.
- Включает ALE-240: единая локальная кнопка "Назад".
- Включает ALE-241: вкладка "Кавалеры", год рождения и действия наград.

Проверки:

- Owner/manual QA PASS.
- Unit tests: 327 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Direct route smoke: PASS.
- Package SHA256 фиксируется в `latest.json`, GitHub Release и финальном отчёте после сборки.
- Public verification перед Telegram обязательна.

## v0.1.12

Статус: выпущено.

Дата релиза: 2026-07-03.

Тип: hotfix.

Состав:

- Включает стабильную базу v0.1.11.
- Включает ALE-228: убран эффект "браузер внутри браузера" на standalone-карточке кавалера.
- Карточка кавалера использует основной scroll страницы вместо вложенного full-page scroll.
- Functional scroll блока "Награды" сохранён.
- Фото-блок, lightbox, `/persons/{id}/photos`, Legacy, Search и Summary не сломаны.
- ALE-227 не включён и остаётся отдельной pending-задачей.

Проверки:

- Owner/manual PASS по ALE-228.
- Unit tests: 299 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Package SHA256: `b8cb2c5e8f74224d7f4f729476eca8cf914c3709325789b062ecdb685ddbf28a`.
- Public verification перед Telegram обязательна.

## v0.1.11

Статус: выпущено.

Дата релиза: 2026-06-26.

Состав:

- Включает стабильную базу v0.1.10.
- Включает ALE-222: loading state на вкладке "Награды", улучшенный typeahead по ФИО, навигация Arrow/Page/Home/End, удаление нижней дублирующей кнопки "Показать все фото".
- Включает ALE-223: кнопка "Назад" в карточке кавалера, удаление дублирующего инфо-блока, увеличенные главное фото/биография/ссылки, фото в два ряда.
- Включает ALE-224: длинные фильтры поиска, пагинация по 50 строк, синхронная высота строк, полный CSV export.

Проверки:

- Owner/manual PASS по ALE-222, ALE-223, ALE-224.
- Unit tests: 299 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Package SHA256: `80e23581d58457d77e6c3a3021164ba4ec033acff6556a411fdf0730742b3fdb`.

## v0.1.10

Статус: выпущено.

Дата релиза: 2026-06-24.

Состав:

- Включает стабильную базу v0.1.9.
- Включает ALE-218: Windows Edge layout карточки кавалера, compact labels ссылок и cache-busting CSS/JS.
- Включает ALE-219: полный lightbox из правого блока "Фото" во вкладке "Награды" и корректный возврат из `/persons/{id}/photos`.
- Включает ALE-220: подблок "Документы" в правом блоке "Фото" на вкладке "Награды".
- Для `/legacy?tab=rewards&person_id=77` visible thumbnails остаются компактными, а full lightbox содержит 16 фото.
- Для `person_id=77` учётные карточки 1/2 показывают "Нет фото", наградные книжки 1/2 берутся из `Source/77/FotoBook1.jpg` и `Source/77/FotoBook2.jpg`.
- "Показать все фото" остаётся отдельным обзором, но не является единственным способом увидеть полный набор.

Проверки:

- Unit tests: 292 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Windows VM QA по ALE-218: PASS.
- Owner/manual check по ALE-219/ALE-220: PASS.
- Package SHA256 фиксируется в `latest.json`, GitHub Release и финальном отчёте после сборки.

## v0.1.9

Статус: выпущено.

Дата релиза: 2026-06-14.

Состав:

- Включает стабильную базу v0.1.8.
- Включает ALE-197: fix-pass slideshow всех фото и компактной карточки кавалера после проверки v0.1.8.
- `/persons/{id}` формирует полную lightbox-группу фото кавалера.
- В обычную листалку входят основные фото, фото наград/документов и безопасные дополнительные фото из каталога кавалера.
- Дополнительные фото листаются без обязательной кнопки "Показать все фото".
- Lightbox убирает дубли, absolute paths в UI не раскрываются.
- Unsafe files не добавляются.
- Карточка кавалера заметно уплотнена: добавлены viewport-limit и внутренние scroll-блоки.
- Фото не раздувают карточку, horizontal overflow не обнаружен.

Проверки:

- Unit tests: 284 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Smoke: PASS.
- Package SHA256 фиксируется в `latest.json`, GitHub Release и финальном отчёте после сборки.

## v0.1.8

Статус: выпущено.

Дата релиза: 2026-06-14.

Состав:

- Включает стабильную базу v0.1.7.
- Включает ALE-195: компактная карточка кавалера после double click.
- Slideshow карточки кавалера дополняется безопасными фото из каталога кавалера.
- Дубли фото убираются, absolute paths в UI не раскрываются.
- CSV boolean `true/false` заменены на `1/0`, Excel-friendly формат сохранён.
- Save As честно объясняет, что браузер не передаёт приложению путь выбранной папки.
- В "Сводной таблице" добавлен resize колонок и строк.
- В "Поиске" мини-фото масштабируются при изменении ширины колонок и высоты строк.
- Lightbox после resize работает.

Проверки:

- Unit tests: 283 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Browser smoke: PASS.
- Package SHA256 фиксируется в `latest.json`, GitHub Release и финальном отчёте после сборки.

## v0.1.7

Статус: выпущено.

Дата релиза: 2026-06-12.

Состав:

- Включает исправления v0.1.5: Excel-friendly CSV, карточка кавалера, справочники, "О программе", редактируемое название программы, биография, компактная форма редактирования, Save As fallback.
- Включает исправление v0.1.6 / ALE-189: компактные мини-фото в поиске, frame 44x44 px, изображение до 40x40 px, placeholder такого же размера, lightbox сохранён.
- Включает ALE-192: быстрый поиск ФИО через явное поле, Enter открывает первое совпадение, список не автофокусится после загрузки.
- Resize-ручки колонок и строк в поиске стали заметнее.
- Save As честно объясняет, что браузер не может автоматически открыть локальную папку.
- Fallback download и "Открыть копию файла" сохранены.

Проверки:

- Unit tests: 282 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Browser smoke: PASS.

## v0.1.0

Статус: выпущено.

- Первая Windows portable preview-сборка.
- Основной legacy-интерфейс.
- Исправления Windows media.
- Базовая проверка обновлений.

## v0.1.1

Статус: выпущено.

- Update progress UI.
- Фильтры и итоги главного экрана.
- Поиск и справочники из форм.
- Возврат из карточки кавалера.
- Telegram-уведомление о релизе.

## v0.1.2

Статус: выпущено.

Release URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/tag/v0.1.2
```

Public latest.json:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

SHA256:

```text
e220c7d5cba8e1b01cab48bdbb172f37e5c349c23f141091206bcc5fd696b103
```

Состав:

- Сводная таблица-шахматка.
- CSV шахматки.
- Каталог и архивирование кавалера.
- Системный выбор места сохранения.
- Браузерный Save As для архива кавалера, PDF-буклета и CSV; native Windows Chrome/Edge dialog нужно подтвердить на стороне владельца.
- Zoom / pan / reset фото.
- Вставка фото из буфера.
- PDF-буклет кавалера.
- Рабочий режим записи.
- Каскадные справочники.
- Обязательные поля.
- Улучшенный поиск.
- Полировка форм.
- Главный экран: сортировка, быстрый поиск, внутренний скролл наград, единые фото-фреймы.
- Улучшенный поток добавления кавалера и наград.
- Перенос длинных ФИО, ссылок, биографии и комментариев в карточке кавалера.

## v0.1.3

Статус: выпущено.

Release URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/tag/v0.1.3
```

Public latest.json:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

Состав:

- Исправленные фото-фреймы на главном экране и карточке кавалера.
- Центрирование фото внутри рамки без растягивания и искажения.
- PDF-экспорт сводной таблицы.
- PDF-экспорт режима "Шахматка по кавалерам".
- Учёт выбранных фильтров в PDF.
- Понятное сообщение для слишком широкой таблицы.

## v0.1.4

Статус: выпущено.

Release URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/tag/v0.1.4
```

Public latest.json:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

Состав:

- Главный экран "Награды": выбранный кавалер остаётся видимым в левом списке.
- Дополнительное подтверждение удаления кавалера.
- Закреплённая строка итогов.
- Компактная форма редактирования кавалера с фотографиями в первом экране.
- Сохранение и отображение краткой биографии.
- Сводная таблица: каскадные фильтры и сортировка шахматки.
- CSV: подсказка после сохранения.
- Поиск: поиск по номеру награды и сортировка результатов.
- Новые признаки фото и документов в поиске и CSV.
- Clipboard-фото сохраняются как JPEG.

## v0.1.5

Статус: выпущено.

Release URL:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/tag/v0.1.5
```

Public latest.json:

```text
https://github.com/drthalas/Fedorinov_rewards/releases/latest/download/latest.json
```

Состав:

- CSV-файлы открываются в Excel корректно по колонкам.
- Карточка кавалера стала читабельнее: ФИО, звание, дата и ссылки не схлопываются в узкие колонки.
- Save As для PDF-буклета и CSV получил fallback обычной загрузки и понятные сообщения.
- Справочник "Звания / специальности" сортируется по алфавиту.
- Во вкладке "О программе" отображается дата версии.
- Название программы можно редактировать и сохранять.
- На вкладке "Награды" добавлена клавиатурная навигация по списку кавалеров.
- Добавлен быстрый поиск по первым буквам ФИО прямо в списке кавалеров.
- Краткая биография сохраняется и отображается после перезагрузки.
- Форма редактирования кавалера стала компактнее.
- Во вкладке "Поиск" добавлен режим мини-фото вместо признаков `0/1`.
- Мини-фото открываются в существующем просмотрщике с zoom/lightbox.
- Таблицу поиска можно настраивать по ширине колонок и высоте строк.
- При поиске по наименованию награды добавлены колонки фото наградной книжки, сторона 1/2.

Known note:

- Windows native Save As через отдельную Windows VM пока не проверялся владельцем; проверка отложена и не блокирует релиз.

## v0.1.6

Статус: выпущено.

Состав:

- Исправлен режим "мини-фото" во вкладке "Поиск".
- Фотографии в таблице показываются компактными превью и не раздувают строки.
- Placeholder для отсутствующих фото имеет такой же размер.
- Полное фото открывается по клику в существующем просмотрщике.
- Lightbox/zoom, resize колонок/строк и CSV остались рабочими.

Known note:

- Windows native Save As через отдельную Windows VM остаётся отложенной проверкой владельца и не входит в v0.1.6.
