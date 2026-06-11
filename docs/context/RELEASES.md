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

Сначала dry-run:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --dry-run
```

Если текст корректный:

```sh
python3 scripts/send_release_notification.py --version X.Y.Z --manifest dist/latest.json --send
```

Не отправлять Telegram, если release/latest.json не проверены.

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

Статус: готовится к выпуску.

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
