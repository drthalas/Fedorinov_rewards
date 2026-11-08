# ALE-528 — durable delivery preview pilot

## Результат

**STOP OWNER DELIVERY PREVIEW E2E PASS.**

Пилот: [ALE-533](https://linear.app/drthalas/issue/ALE-533/t1-delivery-pilotale-528-utochnit-rekomendaciyu-o-rezervnyh-kopiyah),
revision **2**, contract hash `474cd1dc2fa195037ae7bacaa10865fc4dd2287d05af9d893f382906d50be4e0`.
Реальный Owner Telegram → контекстный аналитик → явное подтверждение → Linear → worker claim →
изолированная реализация → focused checks → Railway → одно автоматическое сообщение Owner.

**OWNER QA URL:** [О программе](https://kavaleris-rewards.up.railway.app/legacy?tab=about).
Существующая авторизация стенда сохранена; credentials в URL/отчёт не включаются.
Это Railway handoff, physical Windows runtime на данном этапе — not applicable.

| Identity | Значение |
| --- | --- |
| App base | `41f36c28fe98c19f364a1efa22e501b4df67edcd`, принятый 2.0.32 |
| Worker task branch | `delivery/5f29d200a8aa4c4494b8812abbb6eaf0-r2` |
| Source HEAD | `62c4307c60d3078a97c23bfc1f73059c2f4aba65` |
| Deployed HEAD | `62c4307c60d3078a97c23bfc1f73059c2f4aba65` |
| Railway project/service | Fedorinov Rewards Preview / fedorinov-rewards-preview |
| Final deployment | `28fb88e8-4977-4c08-96aa-7055c56b6880` |
| Owner ready notification | API message_id **72**, одна outbox запись |

Исходная живая session/branch не переключалась:
`drthalas/ale-528-telegram-bot-serheya-avtonomnii-potok-t1t2`, base `fb526fa`.
Рабочая копия main не менялась. Код worker находится в этой ветке, продуктовая правка — в отдельной
ветке/worktree выше. В Docker попал backend 2.0.32 этого exact source HEAD с принятой Linux-обвязкой;
backend 2.0.30 из bot-ветки на стенд не выкладывался.

## Scope пилота и Owner retest

T1 — только справочное предложение в `backend/app/templates/legacy.html`:

- Было: «Рекомендуется делать регулярно.»
- Стало: «Рекомендуется регулярно создавать резервные копии.»
- Экран «О программе» → строка «Резервные копии».
- Frozen: всё остальное в абзаце, остальные строки, HTML, CSS, маршруты и поведение.

1. Открыть OWNER QA URL с прежними credentials.
2. Проверить новое предложение и следующий неизменный текст: «Удаление требует подтверждения и проверяет ссылки на материалы.»
3. Reload: оба предложения сохраняются, version 2.0.32, оформление не изменилось.
4. При необходимости открыть защищённый `/preview/identity`: `source_head` должен равняться exact HEAD выше.
   Прежнее UI-поле Commit остаётся `unknown`; identity подтверждается endpoint + SSH hash каждого backend файла.

Реальный headed Playwright click «О программе» + reload выполнен. Snapshot и screenshot подтвердили
точный текст, frozen предложение и оформление; в свежем QA browser console Errors=0/Warnings=0.
HTTP guest UI/API=401, updater=404, авторизованный About=200. CLI network command в установленной версии
не поддержан; использованы отдельные HTTP checks и полный SSH manifest check, а не фиктивный network PASS.
QA browser оставлен открытым; оба сервиса работают. Новые writes в данных стенда не выполнялись.

## Контур исполнения

`scripts/sergey_delivery.py` — SQLite WAL/FULL state, jobs/operations/events, отдельный process flock.
Атомарный claim, lease 30 с, heartbeat каждые 5 с, fencing generation, одна active job slot.
Пилот остаётся в `preview_ready` и удерживает slot до дальнейшего Owner решения.
Candidate poll и read-only monitoring exact Linear issue — каждые 300 с; general queue выключена.
При изменении Description/hash preview инвалидируется без повторного исполнения.

Private config разрешает только issue ID/UUID/revision/hash ALE-533 r2 и только `implement` +
`railway_preview`; `general_queue=false`, `release=false` обязательны в validator.
Marker DELIVERY PILOT сам по себе не даёт разрешения. Проверяются реальный intake Owner, confirmation,
revision, actual Linear creator/project/team/state и canonical Description. Любой TEST контракт отклоняется;
исторические ALE-529–532 навсегда запрещены отдельным denylist независимо от их статуса/меток.

Исполнение минимального пилота — read-only Codex structured patch proposal, затем проверяемый code applier.
У модели отключены shell/apps/MCP/web/subagents и нет executor credentials. Изолированная task branch
указана в Linear Description; callback/контракт не меняет ветку живой intake-сессии.
До commit проверяется реальный git diff относительно pin base: ровно path/old/new, никаких extra files.
T1 допускает только plain documentation copy без markup/logic. T2 ограничен templates/static и
эскалирует protected areas, JS dependencies, network/credential constructs; общий T2 rollout не включён.
Jinja AST parse полного template PASS; после commit проверены clean tree, ancestry и remote branch parity.

`scripts/sergey_delivery_railway.py` — фиксированные Preview project/env/service/volume IDs, read-only
fingerprints, source-only staging, deploy intent/receipt, reconciliation по точному cliMessage,
SSH/HTTPS code/data/auth verification. Неизвестный ответ upload не приводит к повторному up.
Одна успешно сохранённая реализация/commit; уведомления идут через прежний intake outbox с устойчивым
ключом job+source HEAD. Worker не имеет BOT token и не создаёт обходной sender.

## Recovery и pause/cancel

- Реальный restart сразу после claim: стадия claimed, side-effect operations=0; после restart fence 1→2,
  тот же job/revision. Одна implementation receipt и один source commit.
- После `preview_ready` выполнен ещё один restart: HEAD/deployment/message_id 72 и operation count
  не изменились, повторного model execution/upload/уведомления нет.
- TEMP checks: lease collision/expiry/fence, one active slot, cancellation без requeue, pause до claim,
  recover notify enqueue, scope/markup/protected risk rejection, uncertain upload read-only reconciliation,
  сохранность tracked app assets и отказ upload credentials/DB.
- 51/51 focused intake+analyst+delivery tests PASS. Прежние 41 regression checks сохранены.
  Full product suite не повторялся: product backend bot-ветки не менялся, его прежний unrelated NOT PASS
  не выдаётся за зелёный результат. Для product T1 pilot выполнены focused parse/diff и реальный browser flow.

Owner bot commands: `/delivery_status`, `/delivery_pause`, `/delivery_resume`, `/delivery_cancel ALE-533`.
Также общий `/pause` блокирует новые delivery steps. Уже отправленный Railway request не отзывается;
cancel останавливает следующие gates/notification и не делает неожиданный rollback.
CLI status:

```sh
python3 scripts/sergey_delivery.py status --config data/sergey-delivery/pilot.json
```

Private state/credentials раздельны: intake SQLite/credentials и `data/sergey-delivery/delivery.sqlite3` /
`credentials/executor.json` (0600). LaunchAgent `ru.fedorinov.sergey-delivery` отдельный от intake.
Все config/state/logs/browser artifacts/worktrees в ignored `data/sergey-delivery/`; секреты не в Git.

## Safety и корректирующая сборка

Owner зарезервировал shared preview exclusively для ALE-528. Перед up проверялись текущий deployment,
одна replica и тот же volume `/data`; unexpected/competing deployment блокирует upload.
До/после совпали:

| State | Fingerprint |
| --- | --- |
| SQLite snapshot | `35da52da82e8b625975dadb7ff2e166b345923cfc9b11fcbd9e48010cbd36989` |
| Media | `5892d189b5f2f885c5b181ace4b2030308be4a9022c59ecac817c78db5ea8fb8` |
| Counts | 137 persons, 323 rewards, 888 files |
| Signing/auth | hash parity PASS; private before/after evidence, secret values не выводятся |

Были **две явно различимые preview build attempts**, а не две реализации:
1. `8db2a4fc-67db-428a-b54b-4ea8104c0e37`: Railway SUCCESS, но validation остановила pipeline —
   CLI gitignore исключил tracked JPG/PNG. Browser подтвердил 404. Owner ready message не отправлялся.
2. Corrective build 2 `28fb88e8-4977-4c08-96aa-7055c56b6880`: тот же source HEAD/контракт;
   source-only context с whitelist и `--no-gitignore` сохранил app assets. Все backend file SHA совпали.

Перед correction отдельно доказана сохранность data/media/signing/auth; прежние receipts архивированы
как deployment_build_1/before_build_1. Не было слепого retry/reimplementation; recovery не создавал новую сборку.

Временный Railway SSH key создан отдельно после прямого Owner «да», без переиспользования GitHub/Windows keys.
Использован уже принятый known-host fingerprint ALE-526 с `StrictHostKeyChecking=yes`.
После пилота регистрация key отозвана, обе созданные local private/public copies удалены; другие SSH keys/config
не менялись. После preview_ready worker выполняет только Linear monitoring, SSH key ему больше не требуется.

Private evidence (0600): `delivery-e2e-evidence.json`, `restart-after-claim.json`,
`restart-after-preview-ready.json`, `baseline-fingerprint.json`, browser/output/playwright и browser-acceptance.json.
Credentials не входят в эти файлы. Production/main merge/version bump/Windows/candidate/latest.json/release/Telegram
Сергею не выполнялись. Next stage требует отдельного Owner решения; текущий general queue/release остаются false.

Timing: план 60–90 мин, фактически около 145 мин с финальным cleanup/evidence/handoff. Превышение —
регистрация/strict SSH handoff, выявленный ignore-filter defect, необходимый corrective build/browser
verification и оформление доказательств. Новые широкие проверки
после бюджета не запускались; выполнялись только действия для устранения конкретных failures и cleanup.

## Owner acceptance → candidate / physical gate, 08.11.2026

Owner feature PASS ALE-533 revision 2 принят в актуальном ACTIVE ALE-528.
Продуктовый HEAD остаётся `62c4307c60d3078a97c23bfc1f73059c2f4aba65`, framework продолжен от `ea3f14c`.
На этой фазе production/main и общая очередь остаются выключены; Сергей не участвует.

`scripts/sergey_acceptance.py` добавляет отдельный durable permission gate в intake meta/outbox.
Его identity включает issue/revision, source/deployed HEAD, deployment ID, hashes актуальных
ALE-533 и framework scope. Перед arm выполняются read-only Linear identity/contract checks,
clean product worktree/HEAD, authenticated HTTPS identity и проверка текущего SUCCESS deployment Railway.
Разрешён только принятый ALE-533 r2 product HEAD; arm/restart с тем же identity не дублирует сообщение.

Owner получил сообщение бота №75: «Разрешить candidate + Windows» / «Отложить».
Callback проверяется обычным private-chat allowlist, ролью Owner, одноразовым token, точным
message_id отправленного outbox receipt, waiting-state, expiry 24 часа и pause/cancel.
Записываются реальные callback/update/message IDs. Чужие, старые, повторные, deferred/expired
кнопки и uncertain send receipts не разрешают переход. Callback не запускает updater или packaging.
Непосредственно перед каждой из этих стадий обязательна свежая проверка:

```sh
python3 scripts/sergey_acceptance.py check --config data/sergey-delivery/pilot.json
```

`check` повторно читает actual Linear/product/Railway и сверяет их с настоящим approval.
Изменение любого identity поля требует нового запроса приёмки. `status` читает durable состояние,
`arm` создаёт сообщение только после preflight. Реальные approvals агент за Owner не нажимает.
Следующее продолжение после callback: packaging exact product lineage с минимальными version metadata,
без framework-кода; затем отдельный physical handoff на COPEW-04C68047F с manifest/SHA/ZIP,
свободными writers, свежим verified online SQLite backup, существующим Public Current/BAT и Edge.
REAL test writes запрещены; production потребует следующего разрешённого этапа.

Worker monitoring учитывает явно pinned Owner PASS header только после preview_ready и только
если весь исходный контракт сохранён. Новый header сам не разрешает reimplementation/deployment.
Исходный job ID/contract hash и все receipts сохранены, general_queue/release=false.

TEMP/focused проверки: 60 PASS (9 новых acceptance checks): allowlist, wrong message/action/token,
expiry/defer, pause/cancel, changed identity, повтор/reopen, свежий deployment/revision preflight,
pin заголовка только для готового preview и сохранённого original contract.
Существующие ResourceWarning о незакрытых test SQLite connections остаются; failures нет.
Product/full suite/VM не повторялись — accepted product не менялся. Native Telegram QA URL: n/a.
На checkpoint `waiting`: candidate/Windows/REAL ещё не затронуты; STOP READY FOR OWNER TELEGRAM APPROVAL.

## OWNER PHYSICAL UPDATER PILOT PASS — 08.11.2026

Настоящее Owner approval: callback update `915725225`, исходное сообщение `75`.
В начале продолжения worker оставался preview_ready; candidate ещё не запускался.
Owner получил уведомление начала `78`. Следующий единственный apply выполнен агентом по этому
разрешению и актуальному ACTIVE ALE-528; production/general queue остаются false, Сергей не участвует.

Candidate собран **один раз** из принятой product-линии:

| Provenance | Value |
| --- | --- |
| Accepted product HEAD | `62c4307c60d3078a97c23bfc1f73059c2f4aba65` |
| Candidate/package HEAD | `c6ff156f3c2212dd27ec416a15b82c56f4963db8` |
| Version | `2.0.33`, date `2026-11-08` |
| Metadata delta | только `backend/app/version.py`, `release_notes/2.0.33.md` |
| ZIP | `FedorinovRewards_WebPreview_v2.0.33.zip`, 1,468,737 bytes |
| SHA256 | `7312f48f8ed9cc0fd0cee8fcfcffaaae9fb96cbef27292fd29e3aada0b261a9e` |

Изолированная product-ветка `delivery/5f29d200a8aa4c4494b8812abbb6eaf0-r2-candidate` сохранена/pushed.
ZIP не содержит framework/REAL DB/media/secrets. Package safety, ancestry, accepted template parity,
manifest/version/SHA и HTTP byte parity существующего private LAN Owner channel PASS.
Historical bytes предыдущего channel сохранены; production GitHub Release/latest не менялись.

На physical `COPEW-04C68047F` использована фактическая постоянная установка
`C:\Users\codex\Desktop\Fedorinov Rewards - Public Current` и её существующий `start_windows.bat`
через прежнюю interactive launch task. Установка/BAT/.env/ACL не пересоздавались.
Перед apply: только три собственных runtime Python процесса, localhost 8080 принадлежал ожидаемому
backend, сторонних потенциальных writers нет, свободное место >1 GiB. Свежий SQLite online backup
в отдельном `updates/backups/ale528-533-online` проверен integrity/count/logical parity.
REAL не использовалась для тестовых Add/Edit/Delete или failure tests.

Реальный Edge 151 в console session 2: About 2.0.32 → штатная «Проверить обновления» →
виден candidate 2.0.33 → checkbox restart → «Обновить» → штатный confirm → automatic restart.
Apply только один; durable intent записан до submit/confirm, receipts сохраняют факт попытки и completion.
Upgrader `success`, `10:19:51–10:20:06 UTC`, backend PID `17012 → 8980`, health OK.
Installed SHA совпали для всех **182** файлов exact ZIP. `.env` и BAT SHA сохранены.
SQLite integrity OK, logical SHA и все table counts совпали: 13,708 persons / 24,334 rewards.
В Edge проверены ожидаемая надпись и неизменный соседний текст, открыта карточка `person_id=1295`,
галерея из шести загруженных реальных изображений и отдельный viewer фото (480×288).
Edge оставлен на `http://127.0.0.1:8080/legacy?tab=about` на physical Windows с версией 2.0.33;
runtime и bot services остаются работающими. Не требуется повторный BAT после штатного restart.

### Сокращение проверок и границы evidence

До уточнения Owner был избыточно выполнен полный read-only baseline media fingerprint:
59,866 файлов / 58,957,465,998 bytes, **476.81 с**. На момент нового ACTIVE он уже завершился;
активного обхода не было, никакие процессы для отмены не завершались. После apply полный checksum
**не выполнялся**. Выборочная карточка/галерея/viewer доказывают доступность этих данных,
а не byte parity всей медиатеки после обновления.

Новый Owner header сокращения проверок pinned отдельно. Его удаление из Description должно давать
точно исходный approved framework scope; product/issue/revision/build/callback остаются неизменными.
Любое иное изменение header/original scope по-прежнему блокирует live `check`.

В Railway adapter действительно был обязательный полный media hash. Теперь обычный путь T1/T2 —
bounded sample (до двух файлов на root, до восьми суммарно; ограничены поиск directories/entries
и размер sample). Receipt явно сообщает `media_check_scope=sample`,
`media_tree_byte_parity_checked=false`. Полный обход требует отдельного pinned proof с kind
`owner_request`/`media_lifecycle_risk`, evidence и exact contract hash. Смена policy между сохранёнными
before/after receipts блокируется для явной сверки. Updater/packaging/product не менялись.
TEMP tests запрещают `rglob` в sample режиме и демонстрируют, что изменение unsampled файла
не доказывается sample, но обнаруживается explicit full mode. Все **64 focused framework tests PASS**;
full product suite/VM повторно не запускались. Прежние test SQLite ResourceWarning не выдаются за failure.

### Измеренное время

| Stage | Measurement |
| --- | --- |
| Candidate preparation + private channel, wall | 111.10 с (08:47:19.643–08:49:10.746 UTC) |
| Команда metadata commit + build + package safety | 0.221 с tool execution time |
| Лишний baseline full media check | 476.81 с (7 мин 56.81 с), завершён до нового ACTIVE |
| Последний writers + fresh online backup gate | 3.403 с; из них copy/verify 0.907 с |
| Штатный updater + restart | 15 с, по durable updater timestamps |
| Post SQLite integrity/logical + 182 file parity | 1.076 с |

С начала execution до apply прошло **92 мин 29.49 с** wall time; это включает разработку/настройку
framework, диагностику Edge, context/approval/tool ожидания и перечисленные подготовительные проверки,
а не длительность updater. Edge application launcher и installed Edge157 завершались кодом 21;
уже установленный подписанный Edge151 запустился. Renderer был hidden: обычный focus и один End key
на проверенном Default input desktop восстановили visible state, затем все updater действия выполнялись
нормальными Playwright clicks/dialog. Security policies не менялись, unknown processes не завершались.
Временные metadata/focus/app-only capture tasks удалены; full desktop capture был отклонён review и
не выполнялся. Последующий wall interval также включает framework scope-policy fix, TEMP checks и
оформление evidence; его нельзя приписывать времени установки. На gate PASS общий wall был 118.9 мин.

Private evidence (0600, ignored Git): `physical-pilot-pass-evidence.json`, `candidate33-evidence.json`,
`physical/baseline.json`, `physical/backup.json`, `physical/post-verify.json`,
`physical/timing-corrected.json`, app-only browser snapshots/screenshots и photo loaded assertions.
Данные/медиа/секреты не входят в Git. Следующий production шаг требует отдельного Owner authorization;
Needs Test ALE-528/ALE-533 сохранён.

Следующий scoped этап production orchestration и новой личной кнопки Owner описан отдельно в
[SERGEY_PRODUCTION.md](SERGEY_PRODUCTION.md). До её настоящего callback main/production сохраняются;
старое candidate/updater approval не разрешает публикацию.
