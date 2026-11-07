# ALE-528: intake бота Сергея

Канонический scope: [ALE-528](https://linear.app/drthalas/issue/ALE-528/telegram-bot-sergeya-avtonomnyj-potok-t1t2-do-railway-i-reliza-s).
Прочитаны Description от 07.11.2026 и комментарии; на момент начала комментариев нет.
Base: `bd91c28896ceb6769da710b8d5c0b881887bf90d`; исходный worktree был clean, detached HEAD.
Работа ведётся в отдельной новой сессии/worktree; release/research/Railway sessions не используются.

Точный branch: `drthalas/ale-528-telegram-bot-serheya-avtonomnii-potok-t1t2`.
Этап: приём и анализ текстовой постановки, без delivery executor. Test tier реализации — T2 backend-only;
бюджет 20–45 минут. T1 относится к будущей пилотной пользовательской задаче, а не к реализации бота.
STOP `BOT INTAKE READY FOR PILOT` требует реального диалога и подтверждённой Сергеем задачи в Linear.
При отсутствии credentials этот STOP не достигнут: локальные проверки не заменяют пилот.

## Текущий этап: OWNER TELEGRAM E2E

**Результат: OWNER TELEGRAM E2E PASS.** Создана через daemon
[ALE-529](https://linear.app/drthalas/issue/ALE-529/t1-testale-528-ispravit-opechatku-nagrd-na-nagrad-v-testovom-abzace),
после проверки переведена в `Canceled`; история и evidence сохранены. Это только приёмка текстового
Owner E2E, не приёмка всей системы, не пилот Сергея и не разрешение delivery/release.

| Проверка | Фактическое evidence |
| --- | --- |
| Пользовательский transport | Native Telegram @ Alex для текста; уже авторизованный Telegram Web для inline callback. Все принятые события имеют role=owner после проверки настроенного user ID. |
| Отмена | Первый реальный запрос message_id=5 отменён командой `/cancel`; draft cancelled, issue не создавалась. |
| Уточнения и резюме | Реальные messages 9/11/13/15/17/19/21; summary message_id=22, tier T1, acceptance/frozen проверены визуально и в Linear. |
| Подтверждение | Реальный callback update_id=915725201; диалог c5c98c62337d48a2b73ebaded77b4746, revision 1. |
| Linear | UUID c5c98c62-337d-48a2-b73e-baded77b4746, ALE-529, actual createdBy Александр Романов, parent ALE-528, правильные team/project и labels Telegram ALE-528/T1. TEST/ALE-528, execution/release запрещены. |
| Дубли | Повторные реальные callbacks 915725203 и 915725204 на summary 22 до/после штатного restart отклонены; одна Linear operation, поиск по dialogue ID находит только ALE-529. |
| Recovery | После restart сохранены dialogue/issue/offset/sent ledger; `/status` возвращает created и тот же URL, неизвестных операций нет. |
| Cleanup | ALE-529 Canceled; перед отменой добавлен evidence comment, удаление истории не выполнялось. |
| Секреты | Ключ создан вручную Owner, прошёл identity/team/project/schema preflight и сохранён атомарно 0600. Одноразовая форма завершена и закрыта; секретные значения в чат/Git/журнал не выводились. |

Private evidence: `data/sergey-intake/owner-e2e-evidence.json` (0600) + runtime SQLite events/outbox.
Там сохранены прежний отклонённый payload, checkpoint до restart, принятые transport IDs, исходные
сообщения и issue metadata. Файлы игнорируются Git. Сергею сообщений отправлено 0.

Live E2E выявил два отличия настоящего API от fake adapters:

- `IssueCreateInput.id` требует UUID v4; прежний стабильный UUID v5 отвергался. Теперь используется
  уже сохранённый UUID v4 самого диалога. Старый ID дважды проверен read-only как Entity not found;
  только известная TEST-запись исправлена с private evidence и снова обработана daemon, без слепого retry.
- Linear нормализует Markdown-маркеры списков и завершающий newline. Recovery сравнивает текст с
  нормализацией только этих эквивалентных форм; содержание и indentation остаются обязательными.
  Совпадение проверено чтением live ALE-529. Изменённый текст не принимается тестом сверки.

Native координатный клик по inline-кнопке блокировался `noWindowsAvailable`; synthetic callback не
использовался. Авторизованный Telegram Web предоставил доступную настоящую кнопку.
Focused TEMP checks после исправлений: 30/30 PASS. Full product suite/Windows/production — n/a.
Голосовая обработка — **NOT IMPLEMENTED**; LLM contextual analyst и автоматический анализ screenshot
не подключены. Сервис остаётся в full Linear mode, исполнитель и physical updater gate выключены.

Новый верхний ACTIVE ALE-528 заменил текущий пилот Сергея самостоятельным E2E через авторизованный
Telegram-клиент Owner. Сообщения Сергею запрещены. Проверенный transport — установленный Telegram @ Alex;
профиль адресата показывает @dev_rewards_bot. Фактический отправитель первого тестового сообщения
подтверждён daemon как настроенный Owner user ID; ID не подменялся. Bot API не используется как user transport.
Реальный диалог отмены: request message_id=5, update_id=915725192, draft
`0bc7dd5022614bfea51392f0d5683cfe` перешёл в cancelled после пользовательского `/cancel`;
Linear issue не создавалась. Native typeText потерял кириллицу первого тестового текста;
дальнейшие содержательные сообщения следует отправлять Unicode-safe paste.

Для тестовых постановок с маркером `TEST/ALE-528` contract добавляет явные
`EXECUTION_ALLOWED=false` и `RELEASE_ALLOWED=false`, реального инициатора и указание отменить issue после QA.
Private events сохраняют message/update IDs и роль для пользовательских сообщений и callback.
Ни одна такая задача не передаётся исполнителю; весь delivery executor по-прежнему выключен.

### Защищённое подключение Linear

В Linear открыта Account → Security & access → New API key, имя `ALE-528 daemon intake`.
Подготовлены только `Read` + `Create and update issues` (так называется scope `issues:create` в текущем UI)
и только команда Alex. `Write`, `Admin`, `Create comments`, Full access не выбраны.
Отдельного project-only ограничения ключей нет; adapter жёстко использует PROJECT_ID/TEAM_ID/PARENT_ID
и проверяет доступ к ним и идентичность Owner до сохранения ключа и старта full mode.
Создание нового credential завершает Owner в UI; автоматически кнопка Create не нажимается.

```sh
python3 scripts/sergey_intake.py serve-linear-key --state data/sergey-intake/intake.sqlite3 --credentials-file data/sergey-intake/credentials.json
```

Команда печатает URL одноразовой локальной формы. Только 127.0.0.1, случайный порт, скрытое поле,
строгие Host/Origin/CSRF/content-type/size checks, no-store и CSP без внешних ресурсов. Request logging
отключён. Owner сам вставляет ключ и отправляет форму; ключ уходит только в локальный обработчик,
затем api.linear.app для read-only identity/project/schema validation. При ошибке исходный credentials.json
сохраняется, сообщение не содержит ключа. При успехе файл заменяется атомарно с mode 0600, форма очищается,
сервер завершается. Окно ввода ограничено 15 минутами; при истечении времени повторно запустить команду.
В ходе ввода не снимать DOM/AX/screenshot с полем секретного значения.
Есть также `set-linear-key` для ручного ввода Owner в интерактивном локальном terminal через getpass;
передача секрета argv/stdout/chat не используется. Computer Use доступ к macOS Terminal заблокирован;
он не применялся для ввода. Используется localhost форма.

После успешного ввода: проверить snapshot количества updates/drafts/outbox, штатно остановить только
наш LaunchAgent, убрать `--intake-only` из runtime plist, сохранить те же state/credentials paths,
запустить service. Никакую очередь или offset не обнулять. Дождаться connected/running/heartbeat.
Проверка прав создания — одна реальная подтверждённая TEST/ALE-528 issue через daemon, без предварительных
искусственных product tasks. Тестовую issue затем отменить через текущую Linear-интеграцию.

Focused TEMP checks: 29/29 PASS, включая атомарное сохранение ключа, сохранность существующих полей
при ошибке, read-only identity/project preflight, test-only execution guards и transport evidence.
Промежуточные инструкции выше описывают подготовку; итог живого E2E указан в начале раздела.
Голосовая обработка — NOT IMPLEMENTED.

## Подключение после первого этапа

Owner предоставил новый token через системный буфер; значение сохранено только в private credentials.json.
Telegram `getMe` подтвердил отдельного [@dev_rewards_bot](https://t.me/dev_rewards_bot); webhook отсутствует.
Сергей подтверждён единственным allowed user в Picture Colorizer, Owner — его ADMIN_USER_ID,
дополнительно сверенный с allowlist PDLC. Числовые IDs и token в документацию не копируются.
Telegram закрыт по просьбе Owner.

В основном checkout и этом worktree проверены `.env*`, проектные scripts/docs/config, environment и
локальный MCP config: отдельный Linear API credential не обнаружен. `linear.whoami` подтвердил доступ
текущего чата через ChatGPT connection. Credential этой интеграции не извлекался и не переносился.
Отдельный API key нужен текущему standalone Python adapter, а не чтению/записи Linear из этого чата.

Добавлен явный `--intake-only`: Telegram работает с bot token и двумя ID без ключа Linear.
Подтверждения сохраняются как `pending`, Linear API не вызывается, бот явно сообщает, что issue ещё
не создана. После подключения Linear и перезапуска без этого флага та же очередь продолжится один раз.
Обычный full mode по-прежнему отказывается стартовать без ключа. Это не успешный пилот до Linear.
Новые focused checks: 26/26 PASS, включая отложенное подтверждение и переход в подключённый режим.

Для запуска Telegram без Linear используется явная команда:

```sh
python3 scripts/sergey_intake.py run --intake-only --state data/sergey-intake/intake.sqlite3 --credentials-file data/sergey-intake/credentials.json
```

User LaunchAgent использует source-template ниже с добавленным `--intake-only`; запуск при login,
KeepAlive и private logs. Полный end-to-end пилот, LLM-аналитик, автоматические voice/screenshot analysis,
delivery worker и physical updater gate ещё не завершены. Историческое состояние первого этапа ниже
не является утверждением, что предоставленные позднее token/IDs всё ещё отсутствуют.

Фактический handoff подключения: установлен `~/Library/LaunchAgents/ru.fedorinov.sergey-intake.plist`
(mode 0600), label `ru.fedorinov.sergey-intake`, private state/logs в `data/sergey-intake/` этого worktree.
Owner подтвердил ответ бота после `/start` и `/status`; зафиксированы 2 входящих update и 2 успешные
Telegram отправки (API message_id 2 и 4), без черновика/пилотной issue. Проверен штатный restart нашего
LaunchAgent при пустой pending/sending очереди; offset и 2 sent записи сохранены, повторной отправки нет.
После restart проверяются running/heartbeat; процесс оставлен работающим. Reboot/login recovery не проверялся.
Linear остаётся `not_connected`, executor и physical updater gate не подключены.

## Аудит и переиспользование

| Компонент | Результат аудита / применение |
| --- | --- |
| `CODEX_START_HERE.md`, `LINEAR_PROCESS.md` | Применены repo safety и существующая классификация tiers; новые определения tiers не вводятся. |
| `scripts/send_daily_report.py` | Есть urllib transport, discovery recipients и журнал успешных отправок по роли/дате. Discovery chat ID не является проверкой user ID для нового бота. |
| `scripts/send_release_notification.py` | Штатный production sender и `logs/release_notifications.jsonl`: роль, статус, hash сообщения и API message_id. Остаётся точкой release-интеграции; не изменён и не запускался. |
| `backend/app/services/write_guard.py` | Guard продуктовых write routes; не является guard фоновой очереди. Product DB/media не подключаются к intake. |
| Orchestration | В текущем checkout отдельного intake, delivery queue, claim/lease или orchestration guard нет. Создан только intake outbox, без притворного delivery worker. |
| Codex | Установлен `codex-cli 0.157.1`; доступны exec, resume, JSON events, output schema. В локальном config MCP Linear не настроен; Linear connector текущего чата не является credential для отдельного Python daemon. Модель/reasoning не менялись. |
| Постоянное состояние | Отдельный SQLite WAL + FULL sync, transaction, process flock; private permissions. Не использует продуктовую БД. |
| Linear | Через подключённую интеграцию проверен ALE-528 и список labels. Созданы отсутствовавшие `Telegram ALE-528`, `T1`, `T2`, `T3`, `T4`; их несекретные IDs включены в adapter. Реальная пилотная issue не создана. |

Ссылки для последующего SDK worker: [официальная документация Codex SDK](https://learn.chatgpt.com/docs/codex-sdk).
Документация transport: [Telegram Bot API](https://core.telegram.org/bots/api#getupdates),
[Linear GraphQL](https://linear.app/developers/graphql). Клиент проверяет поддержку
`IssueCreateInput.id` introspection-запросом до первой записи; реальный API с credentials ещё не проверен.

## Что реализовано

`scripts/sergey_intake.py` — stdlib-only сервис для Mac mini:

1. Только private chat и проверенный `from.id`, совпадающий с chat ID. Два разных allowlisted user ID;
   usernames и forwarded author не используются для авторизации. Отдельный bot token, без fallback на другие боты.
2. Одна текстовая постановка → экран/navigation → текущее поведение → желаемое → frozen → observable acceptance
   → область риска. Очевидное «не знаю» не засчитывается ответом. Полноценный LLM-анализ не подключён;
   содержательная неоднозначность сверх анкеты остаётся на проверку аналитика/исполнителя.
3. Короткое резюме с предварительным tier. «Создать задачу», «Уточнить», «Отмена».
   Callback связан с диалогом, revision и отправителем. Уточнение инвалидирует старую кнопку.
4. Подтверждение атомарно сохраняет immutable payload в outbox. Issue получает provenance и tier labels,
   parent ALE-528, реальное происхождение от Сергея либо Owner, исходные тексты и message/update IDs.
   Автор Linear остаётся интеграцией. В private chat нет публичной ссылки на сообщение;
   материалы связаны по ID и хранятся в локальном защищённом состоянии.
5. Стабильный client-generated UUID issue; одна запись outbox на диалог. После неопределённого ответа create
   повторно не вызывается: только read-only сверка UUID и точного Description через `reconcile`.
6. Исходящие Telegram сообщения имеют отдельный журнал outbox с API message_id/status.
   После timeout/crash состояние `uncertain`, слепой retry отсутствует. `/status` позволяет явно запросить
   актуальное резюме или ссылку повторно. Уникальность доставки при неопределённом API-ответе не заявляется;
   выбран безопасный STOP вместо риска дублирования.
7. `/status`, `/cancel`, `/new`; Owner `/pause`, `/resume`. Pause блокирует и ожидающие Linear writes.
   Уже отправленный API-запрос не отзывается. `run` пишет heartbeat; read-only CLI status доступен при работающем сервисе.
8. Скриншот сохраняется как Telegram file_id и message ID, без скачивания и визуального анализа.
   При добавлении к готовому резюме требуется повторное уточнение. Голос требует ручной расшифровки;
   автоматическая транскрипция и мультимодальный аналитик — ещё не реализованы.

Консервативный tier — предложение по анкете: документация T1, заявленный локальный UI T2,
неоднозначная область T3, чувствительные данные/системные области T4 и Owner escalation.
Это не полнота классификатора и не разрешение исполнения. Реальный diff, зависимости и тестовый tier
перепроверяются исполнителем; никакой worker сейчас не получает автоматическое разрешение из этой метки.

## Подключение и постоянный запуск

Подготовлено локальное постоянное состояние `data/sergey-intake/intake.sqlite3`, начальный `paused=true`.
Каталог, SQLite, WAL, lock, credentials и logs игнорируются Git. Для автономного сервиса лучше закрепить
абсолютный путь вне удаляемых worktrees и переносить весь state только при остановленном сервисе.
Не указывать продуктовую DB: существующая SQLite без intake application_id отклоняется до записей.

В текущем окружении отсутствуют:

- `SERGEY_INTAKE_BOT_TOKEN`: credential нового отдельного бота, предоставленный защищённо;
- `SERGEY_INTAKE_SERGEY_USER_ID`, `SERGEY_INTAKE_OWNER_USER_ID`: два проверенных user ID;
- `SERGEY_INTAKE_LINEAR_API_KEY`: credential для фонового daemon с доступом к team Alex / проекту.

Наличие токенов других ботов не разрешает их переиспользование. Значения не выводить в чат/Linear/logs/Git
или argv. Использовать environment либо локальный JSON `credentials.json` с полными именами этих ключей,
в каталоге mode 0700, файл regular, текущего пользователя, mode 0600. JSON не shell script.
`SERGEY_INTAKE_LABEL_IDS` — необязательный JSON override mapping origin/T1/T2/T3/T4 при переносе workspace;
по умолчанию используются проверенные labels Alex. Credentials не входят в launchd plist.

Из корня отдельного worktree (python3 должен поддерживать Python 3.10+):

```sh
python3 scripts/sergey_intake.py init --state data/sergey-intake/intake.sqlite3
python3 scripts/sergey_intake.py check-config --state data/sergey-intake/intake.sqlite3 --credentials-file data/sergey-intake/credentials.json
python3 scripts/sergey_intake.py run --state data/sergey-intake/intake.sqlite3 --credentials-file data/sergey-intake/credentials.json
```

`init` идемпотентен: существующую очередь и pause не сбрасывает. Сервис сверяет `getMe`, отсутствие webhook
и привязку bot ID + allowlist к state. Webhook не удаляет. Не создавать второй state для того же бота;
одна production-конфигурация должна указывать единственный стабильный state. `flock` исключает второй процесс
для одного state. Переименование/удаление state и lock во время работы запрещено.

Для launchd подготовлен source-template `scripts/macos/ru.fedorinov.sergey-intake.plist.example`:
заменить placeholders на абсолютные Python/worktree/private state paths, создать private каталог/logs,
сохранить plist в пользовательский `~/Library/LaunchAgents/ru.fedorinov.sergey-intake.plist`, проверить `plutil -lint`.
Затем `launchctl bootstrap gui/$(id -u) <absolute plist path>` и проверить CLI status/heartbeat.
KeepAlive/RunAtLoad восстанавливают процесс после выхода/логина; это LaunchAgent, работа до login после reboot
не подтверждена. Потребность в LaunchDaemon для unattended boot согласовать на этапе service deployment.
До credentials сервис не установлен и не запущен, persistence после reboot ещё не проверена.

```sh
python3 scripts/sergey_intake.py status --state data/sergey-intake/intake.sqlite3
```

Статус содержит pause, offset, heartbeat, количество pending/sent/uncertain операций, без ID получателей/секретов.
Локальные журналы: таблицы `events` и `outbox` того же SQLite; stdout/stderr сервиса — private state directory.
Перед `reconcile` остановить launchd service через `launchctl bootout`, не обнулять очередь,
выполнить команду ниже и вновь запустить service. Неопределённые Telegram отправки вручную не переигрывать.
Если Linear lookup отсутствует/не совпадает, оставить `uncertain`, диагностировать с Owner, не создавать замену.

```sh
python3 scripts/sergey_intake.py reconcile --state data/sergey-intake/intake.sqlite3 --credentials-file data/sergey-intake/credentials.json
```

## Проверка и реальный пилот

Focused TEMP checks: `python3 -m unittest discover -s tests -p test_sergey_intake.py -v`.
Результат 07.11.2026: intake 24/24 PASS; существующие release notification 11/11 и daily report 11/11 PASS,
`plutil -lint` шаблона и `git diff --check` PASS. Проверка игнорирования runtime SQLite Git — PASS.
Покрыты диалог до подтверждения/создания, origin, duplicate update/callback, чужой ID/group,
revision edit, отказ, restart, атомарный rollback offset/ответа, реальный abrupt process exit,
OS lock recovery, неопределённый Linear ответ и read-only reconcile, Telegram timeout,
Owner pause, private config, screenshot context, voice fallback, классификация и защита чужой БД.
Внешние API заменены fake adapters; настоящий Telegram/Linear transport и launchd — not tested.
Product full suite и browser E2E для backend/Telegram этапа — n/a.
`OWNER QA URL`: not applicable (embedded Telegram flow), physical Windows runtime — not applicable на intake этапе.

Owner retest после подключения:

1. Запустить сервис из этой ветки, проверить identity preflight; Owner отправляет `/status`, затем `/resume`.
2. Сергей в отдельном боте выбирает одну согласованную реальную T1, отвечает на вопросы и проверяет резюме.
3. Нажимает «Уточнить», проверяет revision, затем «Создать задачу». Повторное нажатие не создаёт вторую issue.
4. Открыть полученную Linear-ссылку: происхождение от Сергея, исходные сообщения, acceptance/frozen,
   labels Telegram ALE-528 + T1, parent ALE-528. Зафиксировать issue ID и подтверждающие update/message IDs.
5. Проверить рестарт сервиса: диалог/issue/offset сохраняются; Owner pause запрещает новые writes.
6. Оставить сервис работающим, проверить heartbeat, получить Owner acceptance intake. Только после этого
   объявить `BOT INTAKE READY FOR PILOT` с реальным evidence и перейти к следующему этапу.

## Следующие этапы и незакрытые границы

1. Подключить credentials и выполнить текстовый пилот выше. Затем транскрипция и мультимодальный аналитик
   через доступный Codex механизм, без изменения Owner-selected модели и sandbox policy.
2. Durable delivery queue: single active delivery, atomic lease/heartbeat/checkpoints, cancellation,
   ограниченные повторы и recovery. Supervisor/state отдельно; каждая worker session имеет собственную
   feature branch/worktree по issue. Не редактировать одновременно bot branch из worker.
3. Railway exact HEAD + contract revision и явная приёмка Сергея; diff guard и эскалация T3/T4/защищённых областей.
4. Candidate packaging отдельным этапом, затем самостоятельный physical updater gate как обязательная
   часть полного контракта. Проверить занятость COPEW-04C68047F, REAL online backup, существующий BAT,
   реальное обновление previous→target, installed code/data/error evidence, без тестовых REAL writes.
   FAIL/занятость/неполный gate блокируют production. Этот gate сейчас не реализован и не запускался.
5. Exact accepted line и parity с изменившимся main, тот же ZIP, production и существующий release sender/journal.
   Railway acceptance, updater PASS и установка Сергея сохраняются отдельно.

По актуальному ACTIVE Description постоянное делегирование ALE-528 точечно закреплено в
CODEX_START_HERE/LINEAR_PROCESS: для разрешённых T1/T2 после явной приёмки Сергея на Railway агент
самостоятельно проходит physical updater gate; повторное согласование делегирования не требуется.
На intake этапе gate не выполняется; общий ручной Owner flow остальных задач сохраняется. Также Start.bat из Description и
историческое start_windows.bat из context нельзя угадывать: подтвердить фактически существующий путь на Windows.
Переход к автономному приёму delivery T1/T2 требует полного пилота и Owner acceptance системы.
