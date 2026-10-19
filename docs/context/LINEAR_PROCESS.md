# Linear process

## Проект и язык

Linear project:

```text
Кавалеры и награды
```

Все пользовательские titles, descriptions, checklists и comments вести на русском языке. Английский допустим для commit hash, URLs, repository names, branch names и технических идентификаторов.

## Канонический scope и приоритет

- Repo safety/process rules обязательны.
- Актуальный Linear Description — единственный канонический active scope.
- Comments содержат историю, отчёты и evidence и не добавляют новый scope, если Description прямо не говорит обратного.
- `Accepted` / `Frozen` не переделывать; для них выполнять только требуемые regression checks.
- После Owner FAIL обновить Description: оставить актуальные дефекты, принятую часть перенести в `Accepted` / `Frozen`, а несвязанное требование оформить отдельной issue.
- Launch prompt может уточнить или сузить выполнение, но не может расширять scope, противоречить Description или ослаблять repo safety. При конфликте Codex останавливается и сообщает о нём.

## Owner workflow по фазам

**implementation → physical Windows runtime → Owner feature PASS → Owner candidate с обновлением через существующий BAT → Owner updater/product PASS → production + Telegram обоим.**

Основание: [Owner workflow](https://linear.app/drthalas/document/owner-workflow-physical-windows-runtime-i-release-candidate-cherez-990849969b4b) с уточнениями Owner от 19.10.2026 в [ALE-507](https://linear.app/drthalas/issue/ALE-507/owner-candidate-v2028-ale-503504505-ale-506) и [ALE-502](https://linear.app/drthalas/issue/ALE-502/release-telegram-obyazatelnoe-uvedomlenie-owner-i-sergeya-s-razdelnym). Краткий вход: [CODEX_START_HERE.md](CODEX_START_HERE.md#краткий-workflow); release checklist: [RELEASES.md](RELEASES.md#актуальный-workflow). Description определяет scope и ограничения задачи. Явная Owner production authorization после updater/product PASS охватывает всю production-цепочку ниже; повторные разрешения на merge, публикацию и Telegram внутри этого scope не нужны.

1. **Implementation и physical feature preview.** Выполнить проверки назначенного tier на TEMP; затем показать реализацию на физическом Windows `COPEW-04C68047F`, в отдельном runtime/install с открытым Edge и согласованным прежним рабочим SQLite/media profile. Проверить актуальные пути, не подменять данные синтетическими без предупреждения. Mac/VM — инфраструктура разработки, не Owner preview. Запрос «запусти runtime/покажи preview» разрешает этот preview, но не production. Автоматические write-тесты только TEMP; Public Current не затрагивать при feature preview, риск одновременных writers явно сообщать.
2. **Owner feature PASS → Owner candidate.** В feature/release branch использовать exact принятый HEAD; docs-only commits после него включать только если они приняты и разрешены для candidate. Подготовка candidate включает exact ZIP и подтверждённый путь ручного обновления постоянной Owner-установки через существующий пользовательский BAT. Это одна Owner-задача, с внутренним разделением packaging и Windows handoff, описанным ниже.
3. **Owner updater/product PASS.** Owner лично запускает постоянную установку, устанавливает candidate через «О программе → Проверить обновления → Обновить» и проверяет продукт. Только его явное сообщение подтверждает этот PASS; внутренние Codex checks и feature PASS его не заменяют. При FAIL/паузе candidate не мержить и не публиковать в production; сохранять исторические ZIP/manifest bytes, исправленный candidate получает новую patch version.
4. **Production + Telegram обоим.** После updater/product PASS и команды Owner «выпускаем релиз» Codex в одном production execution выполняет controlled merge exact accepted HEAD в main, публикует GitHub Release/tag/public `latest.json` с принятым ZIP без пересборки, подтверждает публичные version/SHA/size/byte parity и автоматически запускает существующий штатный production sender/config для Сергея и Owner. Отдельного разрешения после публикации или перед Telegram не запрашивать. Проверить обе роли и существующую production notification history по версии; известные успешные отправки не повторять. В итоговом отчёте отдельно указать sent/failed и API `message_id` для каждого, не раскрывая chat IDs/token.

### Внутреннее разделение подготовки candidate

- **Packaging на Mac:** собрать exact Owner-only patch ZIP + manifest, выполнить package/version/SHA/byte parity и разрешённую публикацию в Owner channel. Во время этой операции не подключаться к Windows, не запускать там runtime/Edge/updater и не менять `.env`; не выполнять merge/production до Owner updater/product PASS.
- **Windows handoff:** после завершения packaging в рамках разрешённого candidate-задания проверить постоянный Public Current, фактически существующий пользовательский BAT и candidate visibility. Имя/путь проверить на physical Windows (по handoff v2.0.27 — `start_windows.bat`), не пересоздавать установку/BAT. При необходимости разрешено менять только согласованный `UPDATE_MANIFEST_URL`; остальные настройки, ACL и реальные DB/media сохранять. Сам updater apply выполняет Owner. Первый запуск через BAT и автоматический post-update restart — разные действия; ручной повторный запуск BAT нужен только при неудаче автоматического открытия приложения.
- Если scope уже включает packaging и Windows handoff, выполнять их последовательно без новой задачи, промежуточного Owner PASS или повторного разрешения. Если prompt ограничен Mac-only packaging либо Windows-доступ не разрешён, STOP `CANDIDATE PUBLISHED — WINDOWS HANDOFF PENDING`. Не называть такой результат готовым к ручному обновлению; писать «ZIP опубликован, Windows updater visibility НЕ подтверждена». После подтверждённого handoff — STOP `READY FOR OWNER MANUAL UPDATE`, далее действует Owner.

При сообщении «установлена актуальная версия» сначала диагностировать manifest URL постоянной установки, версию `latest.json`, embedded ZIP URL/доступность и сравнение версий; не пересобирать ZIP и не менять updater без evidence и разрешения.

### Telegram в production execution

Использовать существующие штатный production sender, конфигурацию и журнал. Интеграция ALE-502, новый общий cross-session journal/launcher, locking-проект, дополнительные ветки и тесты не являются gates обычной production publication/Telegram. Улучшение sender остаётся отдельной работой и не должно молча попадать в принятый ZIP.

Обычный preflight сохраняется: подтвердить двух различных получателей Сергей/primary и Owner/copy, проверить production release/manifest, штатный текст и имеющуюся историю отправок версии. Если ни одному не отправляли — по одному сообщению обоим; если одному уже успешно отправили — только недостающему. Не отправлять повторно известному успешному адресату. Если штатный sender не позволяет безопасно отправить только недостающему, получатель/история неоднозначны или API дал ошибку — STOP с конкретным blocker/partial FAIL. При неопределённом результате не выполнять слепой retry и не создавать разовый обходной sender. Один primary `message_id` не означает общий Telegram PASS.

После Owner feature PASS не повторять full suite/VM/physical feature acceptance без конкретного blocker или риска updater/recovery/packaging/migration. Переход между внутренними операциями не добавляет новый gate.

## Роли и запускной prompt

### Owner

- Вручную выбирает model и reasoning effort в интерфейсе до запуска Codex.
- Не должен угадывать runtime, порт или соответствующую commit SHA вкладку во время QA.

### ChatGPT-координатор

- Перед каждым запускным prompt сообщает Owner: сложность `XS/S/M/L/XL`, рекомендуемую модель, reasoning effort, test tier, ожидаемое время и stop condition.
- Это human-facing рекомендация, а не команда Codex самостоятельно менять модель в UI.
- В обычном чате ChatGPT не читает локальные repo-файлы автоматически: он опирается на согласованный project context и при необходимости отдельно читает или обновляет документы доступными инструментами.

### Codex

- Выполняет задачу на выбранной Owner модели и не пытается менять model/reasoning effort в UI.
- Соблюдает active scope, tier, time budget, stop condition и safety. При превышении сложности не расширяет работу бесконтрольно, а возвращает blocker или конкретное объяснение задержки.

Запускной prompt должен быть конкретным и самодостаточным: branch/base SHA, точные действия, `Accepted` / `Frozen`, Out of Scope, required evidence, test tier, time budget и stop condition. Для corrective и сложных UI-багов недостаточно фразы «прочитай Linear и сделай».

## Контекст перед задачей

Всегда читать:

1. `AGENTS.md`;
2. `docs/context/CODEX_START_HERE.md`;
3. актуальный Linear Description.

Дальше читать только релевантные context-файлы:

- product/code: `PROJECT_CONTEXT.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `QA_NOTES.md`;
- release: `RELEASES.md`, `CHANGELOG.md`;
- process/docs/merge/diagnostic: соответствующие process/release-файлы.

Для T0/T1 не перечитывать всю историю проекта без необходимости. Перед изменениями проверить branch, clean working tree, base/head и ограничения задачи.

## Test tiers

### T0 Diagnostic

Только необходимые команды и один smoke. Без product code changes, full suite, compileall, Goal Loop и повторного safety audit. Бюджет: 3–10 минут.

### T1 Merge/docs

Ancestry, local/remote parity, clean tree, `git diff --check` и разрешённый список файлов. Product tests не повторять, Goal Loop не использовать. Бюджет: 3–20 минут.

### T2 Narrow fix

Focused tests и один узкий reproduction, зависящий от поверхности:

- UI/browser: browser click-flow;
- backend-only: focused integration tests.

Full suite — один раз после стабилизации, если он требуется scope/tier. Goal Loop максимум 2 итерации. Бюджет: 20–45 минут.

### T3 Cross-flow UI

Focused tests, browser E2E всех затронутых UI flows, full suite один раз перед final commit, runtime identity и Owner QA handoff для локально запускаемого web UI. Goal Loop максимум 3 итерации. Бюджет: 45–90 минут.

### T4 Data/media

Добавляет data/media safety к релевантному T2 или T3: temp DB/media, destructive/shared-reference tests, failure safety и реальные DB/media hashes при реальном риске или явном требовании. Не требует browser/runtime для чисто non-UI data task. Goal Loop максимум 3 итерации. Бюджет: 60–120+ минут.

Не запускать full suite после каждой Goal Loop iteration: во время разработки использовать focused checks, а full suite запускать один раз после финальной стабилизации, если его требует scope/tier.

## Browser-first UI QA

Для локального web UI основной путь — built-in browser / Playwright headed E2E. UI PASS требует реальный click-flow, фактический результат после reload, console/network/application HTTP checks и screenshots, когда они нужны для visual evidence.

File upload/source selection проверять реальными `filechooser`/file input events с temp fixtures. Unit tests, mocks, source ordering и прямые JavaScript-вызовы не заменяют browser acceptance.

Computer Use — только optional diagnostic fallback: best effort, non-blocking, не обязательный QA/release gate и не единственное evidence PASS. Human-required native шаги нельзя называть автономным PASS.

## Runtime identity и Owner QA handoff

Runtime identity и блок `OWNER QA URL` обязательны для feature-задачи с запускаемым web UI. Для Owner handoff по умолчанию это физический Windows `COPEW-04C68047F`, даже если приложение также запускается локально на Mac. Mac/VM URL не заменяет Owner preview. Для docs-only runtime handoff — `n/a`.

Перед переводом такой feature в `Needs Test`:

1. Зафиксировать branch и полный final SHA.
2. В рамках задания с Owner preview запустить свежий QA runtime этого SHA на физическом Windows в отдельной установке и на отдельном порту, не затрагивая Public Current.
3. Проверить согласованный прежний рабочий SQLite/media profile, указать exact URL, port, PID, start time и `TEMP`/`REAL`; любые замены профиля явно сообщить.
4. Подтвердить identity через startup log, cache key, HTML marker или другой воспроизводимый механизм без UI clutter.
5. Выполнить browser smoke с того же URL, который передаётся Owner, и открыть Edge в пользовательской Windows-сессии.
6. Автоматические write-тесты выполнять только на отдельном TEMP DB/media runtime. REAL preview допускает ручные изменения Owner; риск одновременных writers не скрывать.
7. Оставить проверенный Edge и runtime запущенными для Owner.

Финальный отчёт и Linear comment должны содержать `OWNER QA URL`: один clickable URL на физическом Windows, port, PID, start time, branch, полный SHA, TEMP/REAL DB/media, старые URL/порты, которые нельзя использовать, 3–7 коротких шагов и подтверждение, что Edge/runtime оставлены запущенными.

Для native, packaged или embedded flow, когда branch runtime недоступен, указать `not applicable` или `not tested`, дать точную Owner retest instruction и не заявлять косвенный PASS. Эта оговорка не позволяет подменять физический web preview Mac/VM URL. Packaging не запускает Windows; последующий handoff входит в подготовку Owner candidate, если уже разрешён scope задачи. Mac-only scope заканчивается STOP, описанным [выше](#owner-workflow-по-фазам).

## Git, статусы и Owner QA

- Работать только в ветке из Description. `main` изменять только отдельной явно разрешённой merge/release-задачей.
- Corrective iteration — отдельный commit в той же feature-ветке; не amend-ить и не переписывать опубликованную историю.
- Commit/push переводят feature-задачу в `Needs Test`, но не в `Done`.
- Owner feature PASS означает, что feature принята и может быть переведена в `Done`, если в ней не осталось feature work. Следующий Owner-шаг — подготовка candidate с ручным обновлением; controlled merge выполняется после Owner updater/product PASS в рамках одной production authorization.
- Owner FAIL переводит issue в `Needs Fix`; corrective commit не заменяет acceptance.
- Не переводить каждую feature автоматически в «Готово к релизу»: production требует Owner updater/product PASS и явной команды выпускать релиз; внутри production-задания merge, publication и Telegram выполняются одной цепочкой.

После commit/push добавить Linear comment: что сделано, commit hash, проверки, ограничения и Owner QA steps. Для UI включить browser evidence и runtime handoff, если они применимы.

## Релизы и Owner проверка

Следовать [Owner workflow по фазам](#owner-workflow-по-фазам) и [release checklist](RELEASES.md#актуальный-workflow). Задание на Owner candidate охватывает packaging и Windows handoff, если scope не ограничен явно. После Owner updater/product PASS команда выпускать production охватывает controlled merge, tag/GitHub Release/public `latest.json` и штатную отправку обоим; повторное разрешение на каждый шаг не требуется. Version bump/package publication не выполнять вне разрешённого candidate scope, production-действия — вне production scope; docs-only шаг сам их не разрешает. Candidate updater apply выполняет Owner.

Owner feature acceptance проводится до candidate packaging, Owner updater/product acceptance — до merge и production. Owner QA issue для candidate фиксирует конкретный пакет, updater handoff и явный результат Owner; не откладывать этот обязательный PASS до post-release QA. После публикации follow-up issue может учитывать новые замечания, но не заменяет acceptance до production. Commit/push docs-only шага не разрешает включить его в следующий candidate: нужен явный Owner выбор exact candidate HEAD.

## Timing telemetry

В финальном отчёте указывать длительность применимых этапов: investigation, implementation, focused tests, browser E2E, full suite, safety checks, commit/push и runtime handoff. Неприменимое отмечать `not run` или `n/a`.

Если работа превышает ожидаемый бюджет более чем в 1.5 раза, не расширять scope, не начинать новые широкие проверки и не повторять full suite без причины: вернуть blocker или конкретное объяснение задержки.
