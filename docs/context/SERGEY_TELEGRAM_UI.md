# ALE-534: Telegram UI и составная заявка

> Актуальный режим и навигация: [Owner preview pilot](SERGEY_OWNER_PREVIEW.md). Ниже — evidence предыдущего UI-этапа; прежняя двухкнопочная reply keyboard заменена одной «Меню».

**Предыдущий STOP: OWNER TELEGRAM UI READY FOR LIVE TASK.** Продолжена framework-сессия/ветка ALE-528 от `8389fcd`.
Product main/Rewards, опубликованный 2.0.33, старые TEST и действующий delivery/release не изменялись.
Общая очередь выключена. Сергею в этом этапе сообщений не отправляли.

## Личный голосовой прогон Owner

1. Откройте @dev_rewards_bot. Нажмите нижнее «Меню» → `/new` («Создать задачу») или кнопку «Создать задачу».
2. Запишите и отправьте одну/несколько voice штатными средствами Telegram. Можно дополнить текстом и screenshots.
   Самой записью, паузой и остановкой аудио управляет клиент Telegram.
3. Нажмите «Закончить описание». Дождитесь обработки частей и прочитайте расшифровки; длинные материалы
   раскрываются постранично. Ошибочную часть можно повторить или убрать, сохранив остальные.
4. Нажмите **«Всё верно, передать аналитику»**. Ответьте на необходимые уточнения voice, текстом или screenshot.
5. Проверьте итоговые scope/acceptance/frozen и tier. Только отдельная кнопка **«Создать задачу»** создаёт Linear issue.
6. «Мои задачи» → карточка → «Обновить» показывает актуальное состояние и ожидаемое действие.

Reply keyboard: «Создать задачу» / «Мои задачи», `is_persistent=true`, `one_time_keyboard=false`.
Командное меню: `/new`, `/mytasks`, `/help`. Фактическое отображение клавиатуры контролирует Telegram:
клиент может скрывать её при записи/вводе; доступ остаётся через «Меню»/значок клавиатуры.
Переход в меню/список не теряет текущий черновик. Повторное «Создать задачу» предлагает продолжить или
явно отменить неподтверждённый черновик. Текст кнопок не попадает в требования.

Owner лично задаёт следующую реальную задачу. Её текст и приёмку агент не имитирует.
Создание issue не включает общую очередь и не разрешает выпуск неизвестной будущей задачи:
для исполнения потребуется точное scoped pilot разрешение по отдельному согласованному контракту.

## Реализация и guards

- `scripts/sergey_ui.py` использует прежние Store/outbox, Codex analyst, Whisper и vision.
  Новый runtime UI включён в существующем intake daemon; legacy callable intake сохраняется для совместимости.
- Черновик сохраняет ordered sources и шаги collecting/review/analysis/questions/summary/confirmed/created.
  Два разных callback фиксируют завершение материала и передачу аналитику; финальный create — третий отдельный gate.
- `material_jobs` готовит media/ASR по частям, не вызывает полное интервью по первой части. Передача аналитику
  недоступна при pending/error. Download/transcription cache прежнего механизма переиспользуется.
- Ошибка/3 попытки/замена/отмена одной части не стирают остальные. Перезапуск возвращает только read-only
  material job в pending. Revision и state отклоняют старые callbacks и поздние результаты.
- Явные вопросы и ответы связаны с draft ID, question round и настоящими Telegram message/update IDs.
  Сведения о finish/transfer/create попадают в provenance Linear.
- Sticky TEST guard не снимается удалением ошибочной части с TEST marker. UUIDv4, allowlist, final confirmation,
  protected credentials, exact build/release approvals и uncertain-send guards сохранены.
- `task_cache` хранит свежесть Linear отдельно от локального workflow. Собственность проверяется по user ID
  до чтения карточки/API, pagination — по 5. Есть «Активные»/«Завершённые», local drafts и реальные стадии
  из delivery/production receipts; «Выпущено» не выводится по одному лишь Linear Done.
- Карточка содержит tier с названием уровня, настоящий Linear status/update time, локальный этап, ожидаемое
  действие и существующие ссылки Linear/Railway/Release. Offline явно помечает устаревание.
  UI refresh — read-only outbox kind, безопасно восстанавливается без повторного сообщения; linear/telegram
  uncertain writes по-прежнему не повторяются вслепую.

## Фактический Owner E2E

Авторизованный Owner Telegram Web через Chrome → настоящее командное меню → `/new` → отмена пустого
черновика → постоянная кнопка «Создать задачу» → четыре материала:

| Материал | Telegram message / update |
| --- | --- |
| Честная TEST-метка/происхождение | `91 / 915725231` |
| Voice 1, macOS Milena, 10.696 с | `93 / 915725232` |
| Voice 2, macOS Milena, 12.023 с | `96 / 915725233` |
| Синтетический screenshot MM534-MULTI-001 | `99 / 915725234` |

Bot updates действительно имеют kind `voice`, а не document. Whisper автоматически получил два
разных транскрипта. На этом этапе analysis jobs = 0. «Мои задачи» и restart сохранили draft
`202fd2216b50485198164ccb25252a7b`, revision и все четыре части; 3 material jobs остались done/attempts=1.

«Закончить описание» update `915725238` → читаемая сводка/«Раскрыть материалы» →
передача аналитику update `915725240`. Аналитик учёл screenshot и оба voice, спросил только новую
точную формулировку. Ответ message `112`, update `915725241` связан с question round 1.
Итог T1 содержал scope/acceptance/frozen и реальные image observations.
Отдельный create callback `915725242` создал ровно
[ALE-535](https://linear.app/drthalas/issue/ALE-535/t1-testale-528-pereimenovat-razdel-spravki-v-poisk-po-familii).
Повторный click отклонён. Provenance — настоящий Owner, `TEST/ALE-528`, execution/release=false.

Карточка сначала показывала Backlog/TEST guard, refresh сверил статус. Второй restart после создания
не повторил 2 completed model jobs, 3 completed media jobs или единственную Linear operation.
После QA issue переведена в **Canceled**, карточка refresh показала актуальный Canceled.
Проверены обе страницы собственной истории (9 завершённых записей), а также ALE-533:
«Выпущено 2.0.33», Linear Done и все три ссылки Linear/Railway/Release — без новых release действий.

**95 focused tests PASS**: прежние guards/recovery/release плюс 13 новых UI/material/privacy/cache checks.
Failure tests — TEMP. Full suite, Windows/updater/product checks и media scan не повторялись.
Остались прежние test SQLite ResourceWarning; failures нет. Embedded Telegram OWNER QA URL: n/a;
проверка — реальный пользовательский transport. Bot API не использовался для подделки входящих сообщений.

Private evidence (0600, ignored Git): `data/sergey-intake/ale534-ui-e2e-evidence.json`,
`ui-test-fixtures/before-restart.json`, `created-before-restart.json`, audio/PNG fixtures и app-only screenshots.
Перед миграцией сохранён отдельный online backup intake state; Rewards REAL не использовалась.
Сервисы оставлены работающими. ALE-534 требует Owner live test и остаётся Needs Test.
