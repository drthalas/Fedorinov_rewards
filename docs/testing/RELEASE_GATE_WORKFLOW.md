# Release Gate Workflow

Этот документ задаёт постоянный pre-publication workflow проекта Fedorinov
Rewards. Он описывает роли тестовых контуров и обязательную последовательность,
но не утверждает, что все шаги уже автоматизированы.

## Обязательная последовательность

```text
Feature branch
  -> Mac/Linux tests
  -> Windows VM branch-level/pre-merge checks
  -> controlled merge and release candidate preparation
  -> Physical Windows Gate on the exact candidate artifact
  -> only after PASS: GitHub Release, latest.json, Telegram,
     user update availability
```

Этап нельзя считать пройденным по результатам следующего этапа. Публикация не
является способом доставить candidate на первый реальный Windows-тест.

## Роли контуров

### Mac mini

Mac mini — основная dev/control машина:

- хранит рабочий repository checkout и запускает Codex;
- выполняет Mac/Linux tests, static checks и package safety;
- координирует feature, merge и release issues;
- собирает и идентифицирует release candidate;
- управляет Windows VM и physical gate;
- выполняет публикацию и отправку Telegram только после всех gates.

### Windows VM на Mac mini

Windows VM — быстрый branch-level и pre-merge контур:

- `cmd.exe` и BAT parsing;
- Windows-specific unit/integration tests;
- updater/recovery simulation;
- launcher/runtime identity и single-instance checks;
- forced failure/rollback simulation;
- быстрые repeated loops во время стабилизации ветки.

VM должна обнаруживать Windows-specific дефекты до подготовки release
candidate. PASS на VM не заменяет physical release acceptance.

### Physical Windows Gate

Физический Windows laptop — production-like pre-publication gate:

- проверяет exact ZIP, который планируется опубликовать;
- использует реальный Explorer, double-click и штатный пользовательский BAT;
- проверяет видимый browser UX, prompts и folder picker;
- проверяет штатный updater/recovery без dev-only обходов;
- фиксирует DB/media fingerprints до и после;
- подтверждает ровно один app-owned backend и strict runtime identity;
- проверяет forced failure, rollback и повторный обычный запуск;
- выполняет несколько последовательных PASS, когда этого требует release scope.

Подробные machine-specific setup и команды не являются частью этого общего
workflow. Они хранятся в документации physical gate, когда она доступна в
текущей ветке.

## Feature и merge gates

Feature issue определяет необходимые Mac/Linux и Windows VM checks по своей
поверхности и test tier. Windows-specific product, launcher, package, updater
или recovery change без требуемой VM-проверки не готов к controlled merge.

Controlled merge issue:

1. проверяет exact accepted feature SHA и ancestry;
2. выполняет разрешённый merge без переписывания accepted commits;
3. запускает только назначенный merge gate;
4. не публикует release без отдельного release authorization.

Merge в `main` сам по себе не означает готовность к публикации.

## Candidate identity

Release issue создаёт один candidate artifact и до physical gate фиксирует:

- filename и version;
- release commit SHA;
- byte size;
- SHA256;
- package safety result;
- применимый manifest и release notes.

Physical gate и publication должны использовать те же bytes. После physical
PASS нельзя молча пересобирать ZIP. Если rebuild неизбежен, новый ZIP получает
новую identity и повторяет применимые package и physical gates.

## Publication gate

GitHub Release, public `latest.json`, Telegram и доступность обновления для
пользователя разрешены только когда:

1. Mac/Linux release checks прошли;
2. применимые Windows VM checks прошли;
3. exact candidate прошёл Physical Windows Gate;
4. candidate identity совпадает с публикуемыми bytes;
5. release issue явно разрешает публикацию.

Заказчик или пользователь не должен быть первым реальным тестировщиком release
updater/recovery. Запрещён порядок «сначала public release, потом первый physical
Windows test».

## Current automation boundary

Процесс может сочетать scripts и ручные headed checks. Наличие документа не
означает автоматизацию Explorer, prompts, browser UX или rollback.

Текущий `Manual Release` GitHub Actions workflow собирает artifact заново при
каждом запуске. Отдельный dry-run и последующий `publish=true` нельзя считать
byte-identical без независимого SHA256 evidence. Пока workflow не умеет
публиковать уже физически принятые bytes, release должен использовать путь,
который публикует exact accepted local artifact, либо остановиться с отдельной
pipeline follow-up issue. Эта документационная задача не меняет pipeline.

## Если gate недоступен

Codex не подменяет отсутствующий gate unit tests, mock или косвенным smoke.
Отчёт обязан указать:

- какой exact шаг не выполнен;
- почему он недоступен;
- какой release risk остаётся;
- блокирует ли риск публикацию;
- exact follow-up test plan и требуемый контур.

Если невозможно доказать physical acceptance exact candidate или byte parity,
публикация остаётся заблокированной.

## Required evidence

Release evidence должно содержать:

- branch, commit и candidate identity;
- результаты Mac/Linux и Windows VM checks;
- physical host/run identity без secrets;
- headed и automated physical results;
- updater/recovery, single-backend и rollback evidence по scope;
- DB/media fingerprint result;
- final public asset size/SHA parity;
- явно перечисленные skipped/not-applicable checks и residual risks.

После публикации отдельно проверяются public ZIP и `latest.json`. Telegram
отправляется только после public verification и только по явному authorization.
