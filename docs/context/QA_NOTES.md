# QA notes

## Роль Hermes

Hermes — основной тестировщик проекта. Hermes QA подтверждает качество перед релизом и фиксирует PASS/FAIL по пользовательским сценариям.

Без Hermes QA PASS релиз не публиковать.

## Стандартный preflight

Перед задачей:

```sh
cd ~/Projects/Fedorinov_Rewards/Fedorinov_rewards
git status --short
git log --oneline -10
```

Если working tree грязный и задача не про уже сделанные изменения, остановиться.

## Dev data root

Для локального QA использовать:

```text
/Users/hermes/LocalData/FedorinovRewards/Rewards
```

Не трогать:

```text
/Users/hermes/Desktop/Rewards
```

## Baseline counts

Ожидаемые counts после clean QA:

```text
person: 108
rewards: 350
mark: 146
guide: 18
guide_lev_0: 4
guide_lev_1: 11
guide_lev_2: 20
guide_lev_3: 280
guide_lev_4: 143
```

Проверка:

```sh
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards python3 scripts/inspect_local_data.py
```

## Media baseline

Ожидаемый media baseline:

```text
total: 958
existing: 950
missing: 8
```

Проверка:

```sh
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards python3 scripts/check_media_links.py
```

8 missing media paths — известные старые отсутствующие ссылки. Они не должны внезапно расти из-за изменений приложения.

## Правила QA

- Работать только с dev data root.
- QA-записи после smoke удалять.
- Counts после write-smoke должны возвращаться к baseline.
- Физические фото не удалять автоматически.
- Отвязка фото очищает поле в базе, но не удаляет файл.
- Generated PDF, archives, updates и logs остаются ignored.
- Real updater apply не запускать без отдельного разрешения.
- Git status после проверки должен быть clean или содержать только ожидаемые изменения задачи.

## Типовые проверки

Минимум для большинства задач:

```sh
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards python3 scripts/inspect_local_data.py
REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards python3 scripts/check_media_links.py
.venv/bin/python -m compileall backend/app tests scripts
.venv/bin/python -m unittest discover tests
git diff --check
```

Smoke backend:

```sh
WRITE_MODE=true READ_ONLY=false REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards scripts/run_dev.sh
```

Если порт 8080 занят:

```sh
APP_PORT=18080 WRITE_MODE=true READ_ONLY=false REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards scripts/run_dev.sh
```

## Known limitations

- Clipboard paste зависит от браузера и secure context.
- 8 старых missing media paths допустимы как baseline.
- Generated PDF/archives/logs ignored и не должны попадать в Git.
- Автоматический restart после update отложен.
- Read-only/write-mode как пользовательские режимы позже нужно убрать из интерфейса.

## v2.0.1 QA

- Legacy compatibility baseline: public tag `v0.1.14`, commit `53bb35579aeb8a0c26a38c04019de7f7df36645a`.
- Public v2.0.0 ZIP under the legacy updater: expected `forbidden file type` before backup/install.
- Candidate v2.0.1 ZIP: 107 entries, 0 binary image entries, 6 byte-identical UI-assets embedded in packaged CSS.
- Legacy retry E2E on temp install/data/media: v2.0.0 failure -> fresh v2.0.1 metadata/download -> backup -> install -> restarted-process version check -> rollback: PASS.
- Temp DB/photos/documents SHA before/after: unchanged.
- Focused tests: 56 PASS.
- Full suite: 390 PASS; only pre-existing ResourceWarning diagnostics were emitted.
- Package safety, compileall and `git diff --check`: PASS.
- Packaged browser smoke: PASS at 1366x768, 1440x900 and 1920x1080; 6 embedded assets rendered, no HTTP/console errors or horizontal overflow.
- Data baseline: person 108, rewards 351, mark 146, guide 18; levels 4/11/20/280/143.
- Media baseline: total 961, existing 950, missing 11.
- Real DB/media SHA and fingerprint are checked before and after publication; release workflow does not write to real data.

## v2.0.0 QA

- Owner manual QA нового visual redesign на `main`: PASS.
- Unit tests: 377 PASS.
- Browser smoke: PASS на 1366×768, 1440×900 и 1920×1080.
- Temp-only photo upload/replace/clear для persons 77 и 106: PASS.
- Data baseline: person 108, rewards 351, mark 146, guide 18; levels 4/11/20/280/143.
- Media baseline: total 961, existing 950, missing 11.
- Две ранее существовавшие `person_media` записи person 50 ссылаются на существующего person и не изменялись.
- Реальные DB, фотографии и документы не менялись.

## v0.1.14 QA

- Owner manual QA: PASS.
- Unit tests: 346 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media audit на release preflight: total 960, existing 950, missing 10. Две дополнительные отсутствующие ссылки справочника уже были в real DB; релизный проход их не создавал и данные не менял.
- Browser smoke на read-only real DB: PASS; write-smoke выполнялся только на temp DB в ALE-245.
- Реальные данные и фото не менялись.

## v0.1.13 QA

- Owner manual QA перед релизом: PASS ("протестировал, всё хорошо").
- Unit tests: 327 PASS.
- Data baseline: person 108, rewards 350, mark 146.
- Media baseline: total 958, existing 950, missing 8.
- Direct route smoke: PASS.
- Platform note: локальный bind dev-server из Codex sandbox был заблокирован лимитом эскалаций, поэтому автоматический route smoke выполнен in-process; owner manual QA в Chrome на Mac покрывает браузерную часть.
- Реальные данные и фото не менялись.
