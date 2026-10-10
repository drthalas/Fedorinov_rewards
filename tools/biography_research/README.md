# Локальный пилот биографий ALE-491

Прототип работает отдельно от приложения. Он не импортирует backend, не запускает
runtime и не пишет в SQLite. Персональные XLSX, JSON и исследовательские события
хранятся в приватном каталоге вне репозитория. Не отправлять их в Linear/GitHub.

`select_sample.py` запускается на source host с подтверждённым DB path. Он
разрешает только read-only SQLite, одну query-only транзакцию и rollback journal
без sidecars. WAL/journal ambiguity означает STOP, без восстановления. Иерархия
«СССР → Боевые → Ордена → Александра Невского» разрешается через исходные guide IDs.
Pool упорядочен по DISTINCT person.id; seed обязателен. Единственная frozen
selection.json сохраняется локально; повторно не извлекать выборку при resume.

```sh
python select_sample.py --db <verified-source-db> --seed 20261009491
```

Вывод этой команды содержит только выбранные 50 записей и предназначен для
перенаправления в приватный файл через доверенный LAN, а не для терминального лога.

`xlsx.mjs` создаёт новый input или enriched XLSX через bundled artifact-tool.
Задать `ARTIFACT_TOOL_MODULE` из dependency loader; использовать bundled Node.
Выходной файл не перезаписывается. Исходные колонки/значения проверяются перед
экспортом; идентификаторы и номера сохраняются строками. Если исходный SQLite
хранил номер INTEGER, утраченные ранее ведущие нули невозможно восстановить.

```sh
node xlsx.mjs <private>/selection.json <private>/input.xlsx
python runner.py --model <selected-model> --private-dir <private>/compatibility
python research.py <private>/input.xlsx --private-dir <private> --model <selected-model> --limit 5
# Только после реального access/identity PASS первых пяти:
# Private quality_gate.json: {"pass": true, "input_sha256": "<frozen-input-hash>"}
python research.py <private>/input.xlsx --private-dir <private> --model <selected-model> --offset 5 --limit 45
node xlsx.mjs <private>/selection.json <private>/enriched.xlsx <private>/progress.json
```

Research использует установленный Codex CLI с существующим ChatGPT login,
read-only sandbox, ephemeral session и native live web search. Новые API keys,
платные сервисы и глобальная замена модели запрещены. Модель задаётся явно только
для subprocess через `--model`; до реальных запросов обязателен успешный synthetic
inference+web smoke этой же модели через ChatGPT login. API key environment
не наследуется. Не относящиеся к исследованию MCP servers отключены только на
время данного subprocess, без редактирования глобальной конфигурации.
Research передаёт только нужные поисковые атрибуты одной выбранной строки,
заменяя внутренний SQLite person ID псевдонимным row key. Workbook целиком и
технические ID иерархии не передаются. Соответствие row key → person ID локальное.
Capability preflight
должен пройти до передачи персональных запросов. Несовместимая модель или
недоступный подписочный runner означает BLOCKED, а не поиск обходного платного API.

На одну запись отведено до 240 секунд; только реально завершённые IDs при resume
пропускаются. `attempt_state=infrastructure_blocked` и legacy infrastructure
`Ошибка источника` не считаются завершением и могут повторяться. Завершённый
source-result, включая честный source error, сохраняется при resume.
Изменение input hash блокирует resume. Базовые источники — warheroes.ru,
podvignaroda.ru, pamyat-naroda.ru. Проверенный институциональный источник добавлен
узко: `xn----7sbajiedzjdfe3ac7bmi.xn--p1ai`, actual person cards в
`/electronic-database/` либо персонально атрибутируемые записи проверенной коллекции
`/elektronnaya-baza/`. Общая страница без конкретной записи не даёт identity evidence.
Он охватывает отдельные операции Восточной Пруссии/Литвы
1944–45, а не всех кавалеров. `direct_source.py` читает реальные GET, хранит
status/resolved URL/content hash локально, проверяет robots, соблюдает Crawl-delay
10 секунд и общий request budget. Возобновление не обнуляет ledger; cached robots
действует максимум 10 минут. Никаких придуманных URL/slugs или слепой пагинации.
Кодирование query сохраняет семантику form-encoded пробелов. Нет обхода CAPTCHA/login/robots.
Допустимы только реально открытые персональные страницы, а не snippets.
Точное полное ФИО + совпавший достоверный год рождения + та же награда достаточны
для `Готово к проверке` / high confidence. Одна профильная страница достаточна;
звание, часть, номер, архивный документ и второй источник сверх этого не требуются.
При полном ФИО и существенном совпавшем признаке, но неполных трёх полях, разрешён
сourced provisional draft: статус `Требует проверки`, видимый `[Предварительно]`
и конкретная причина неопределённости. ФИО-only, инициалы и противоречия дают пустой
текст. Input fallback 1945 не обеспечивает high confidence без проверенной provenance.
Каждый факт должен иметь source evidence; текст до 600 символов. Релевантные публичные
биографические профили разрешены, общие индексы людей — не provenance для биографии.
Два обычных порядка записи полного имени (ФИО и ИОФ), регистр, пробелы, пунктуация
нормализуются; разные имена или инициалы не подменяются.

`reevaluate.py` создаёт отдельный evaluation/progress ledger для прежних пяти,
не меняя старые результаты и frozen input. Использует cached candidate links,
120-second/3-web-call watchdog и подпись `exact-fio-birth-award-v1`; не запускает 45.
`--ignore-user-config` используется только в slim subprocess, с explicit `gpt-6-sol`,
сохранённым ChatGPT auth и удалёнными API key env. MCP partial overrides в slim
не передаются. Результаты/usage каждого retry сохраняются отдельно, infrastructure
ошибки не считаются завершением исследования.

JSON validation проверяет структуру, но не доказывает историческую истинность.
Первые пять требуют содержательной проверки source/identity evidence перед
45 оставшимися. Для биографий дополнительно проверяются actual open-page события
для каждого cited URL; search snippets не заменяют открытые страницы.
Correction разрешает per-subprocess модель из каталога после реального smoke.
`gpt-6-sol` прошла ChatGPT inference+web smoke; глобальная `gpt-6.1-sol` не изменялась.
Передача реальных персональных строк требует разрешения действующего approval
review. Выборка не заменяется при инфраструктурных ошибках.

Проверки:

```sh
python -m unittest discover -s tools/biography_research -p 'test_*.py' -v
```

Full suite, browser/runtime, VM, updater, продуктовые изменения и SQLite import
не относятся к этому прототипу. Перед импортом требуется отдельное Owner решение.
