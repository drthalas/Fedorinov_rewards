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
WRITE_MODE=true READ_ONLY=false REQUIRE_BACKUP_BEFORE_WRITE=false REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards scripts/run_dev.sh
```

Если порт 8080 занят:

```sh
APP_PORT=18080 WRITE_MODE=true READ_ONLY=false REQUIRE_BACKUP_BEFORE_WRITE=false REWARDS_DATA_DIR=/Users/hermes/LocalData/FedorinovRewards/Rewards scripts/run_dev.sh
```

## Known limitations

- Clipboard paste зависит от браузера и secure context.
- 8 старых missing media paths допустимы как baseline.
- Generated PDF/archives/logs ignored и не должны попадать в Git.
- Автоматический restart после update отложен.
- Read-only/write-mode как пользовательские режимы позже нужно убрать из интерфейса.
