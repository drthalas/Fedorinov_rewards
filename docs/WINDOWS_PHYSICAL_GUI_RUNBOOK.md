# Physical Windows interactive GUI runbook

## Назначение

Этот runbook проверяет и восстанавливает реальный интерактивный Windows desktop для physical release gate. Он не заменяет правила discovery из ALE-353/ALE-366 и не разрешает подменять GUI gate headless/S4U запуском.

Канонические слои независимы:

1. `fedorinov-win-gate` и discovery helper подтверждают сеть, host key и SSH.
2. `sshd`, `TermService` и TCP/3389 подтверждают transport.
3. Активная пользовательская session с `Explorer`, `DWM` и `Winlogon` подтверждает interactive desktop.
4. Limited `InteractiveToken` task `FedorinovRewards-Physical-GUI` запускает видимый Edge в этой session.
5. CDP и screenshot из той же session подтверждают, что browser действительно видим, а не запущен headless/S4U.

Один failed probe не означает, что host выключен. При неполной диагностике статус только `connectivity unresolved`.

## Preflight с Mac mini

Запустить из repository root:

```bash
scripts/physical_windows_gui_preflight.sh
```

Авторизованный RDP login/reconnect запускается отдельным entrypoint:

```bash
scripts/open_physical_windows_rdp.sh
```

Preflight использует:

- SSH alias `fedorinov-win-gate`;
- machine-local discovery helper;
- pinned SSH host key;
- только факт наличия credential reference в macOS Keychain.

Пароль не передаётся в аргументах, не выводится и не хранится в Git, Linear, документации или логах.

Проверенные Windows-side scripts находятся в `scripts/windows/`:

- `physical_gui_preflight.ps1` — read-only session/service/task audit;
- `physical_gui_worker.ps1` — task-owned visible Edge worker;
- `start_physical_gui.ps1` — bounded repeat-safe launcher с CDP/session proof;
- `capture_physical_gui.ps1` — screenshot из interactive session.

Mac-side `open_physical_windows_rdp.sh` получает адрес через canonical discovery, а пароль — только из Keychain через stdin. RDP certificate сохраняется по TOFU при первом доверенном LAN connection; последующее изменение certificate должно останавливать подключение.

## Как читать результат

### Host reachable, interactive desktop ready

Ожидаются одновременно:

- SSH PASS;
- TCP/3389 listener reachable;
- `sshd` и `TermService` `Running`;
- session пользователя приложения;
- `Explorer` и `DWM` в одной положительной session ID;
- canonical GUI task существует с `InteractiveToken`/`Limited`.

После этого можно запускать task-owned Edge worker и требовать CDP плюс screenshot.

### Host reachable, interactive desktop unavailable

Типичный post-reboot state: SSH и RDP работают, но `query session` не показывает вошедшего пользователя, а `Explorer` отсутствует. SSH login не создаёт оконный desktop.

Восстановление:

1. Разрешить адрес только canonical discovery helper-ом.
2. Выполнить authorized RDP login из Mac mini, получая credential из Keychain через stdin.
3. Повторить preflight и подтвердить `Explorer`/`DWM` в новой session ID.
4. Запустить canonical GUI task и проверить Edge/CDP/screenshot.

Нельзя жёстко ожидать session ID `1`: после reboot или reconnect Windows назначает новый ID. Проверяется совпадение session ID Edge, Explorer и DWM.

### Edge завершается без окна или CDP

Проверить по порядку:

1. Не запущен ли Edge через `HighestAvailable`: canonical task должен быть `Limited`.
2. Используется ли отдельный task-owned Edge profile.
3. Не остался ли предыдущий экземпляр canonical task в `Running` при `MultipleInstancesPolicy=IgnoreNew`.
4. Завершить только Edge с task-owned profile, остановить только canonical GUI task, дождаться `Ready`, затем запустить task снова.
5. Проверить Windows security alerts. Не отключать защиту и не применять broad process kill.

`0x80070005` сначала проверяется как ACL/path problem. Worker, request, status, profile и screenshot должны находиться в пользовательском `%LOCALAPPDATA%`, а не в защищённом общем evidence root.

## Canonical task contract

- task: `FedorinovRewards-Physical-GUI`;
- user: локальный пользователь приложения;
- logon type: `InteractiveToken`;
- run level: `Limited`;
- worker window: hidden;
- state/profile: `%LOCALAPPDATA%\FedorinovGate\PhysicalGui`;
- разрешённый target URL: только `http://127.0.0.1:<port>/...`;
- CDP: только выбранный localhost port;
- repeat launch завершает только предыдущий task-owned Edge/profile и canonical task instance.

Task не имеет boot/logon trigger и не запускает product runtime автоматически. Release gate отдельно поднимает exact task-owned application runtime.

## Required gate sequence

Перед physical updater/release acceptance:

1. Canonical discovery + SSH preflight.
2. Authorized RDP login/reconnect.
3. Visible Edge + CDP + screenshot.
4. Повторный Edge launch не менее трёх раз.
5. RDP disconnect/reconnect и повторный launch.
6. Reboot; дождаться SSH/RDP services.
7. Authorized RDP login без физического участия Owner.
8. Повторить visible Edge proof.
9. Idle/session-transition gate; подтвердить отсутствие sleep/lock и сохранение SSH/RDP/Edge.
10. Только затем выполнять updater UI steps.

## Когда нужен Owner

Остановиться и запросить минимальный prerequisite, если:

- credential reference отсутствует или Keychain недоступен;
- RDP отклоняет корректно сохранённый credential;
- Windows требует смены пароля/MFA/interactive consent;
- security policy запрещает RDP или task execution;
- требуется изменение router, firewall, UAC или endpoint protection;
- после canonical reconnect отсутствуют Explorer/DWM и причина не доказана.

Не просить Owner вмешиваться только потому, что console session ID изменился или RDP session была disconnected.
