# Remote Owner Candidate Channel

## Назначение

Каналы обновления разделены постоянно:

- production: публичный GitHub `latest.json`, который использует Сергей;
- Owner candidate: LAN-only endpoint на Mac mini для ещё не опубликованного exact release candidate.

Release-candidate stage обновляет только файлы на Mac mini. Он не подключается к physical Windows, не меняет там `.env`, не запускает приложение или Edge и не проверяет UI. Permanent physical `Public Current` настраивается на endpoint один раз; все последующие candidates появляются там без действий Codex на ноутбуке.

Owner candidate создаётся из exact accepted feature/release HEAD **до** его merge в `main`. На этом этапе `main` остаётся последней Owner-accepted production line. Если Owner отклоняет candidate, corrective work продолжается в той же feature/release lineage, а `main` не требует revert rejected candidate.

Только после manual Owner updater/product PASS и отдельного разрешения exact accepted candidate HEAD контролируемо интегрируется в `main` с ancestry/tree/parity verification. Короткая production publication использует тот же проверенный ZIP без пересборки. Если integration меняет candidate tree или обнаруживает mismatch, publication останавливается и требуется новый candidate gate.

## Canonical endpoint

```text
http://Mac-mini-hermes.local:18387/latest.json
```

Сервис:

- слушает IPv4 на Mac mini;
- принимает запросы только с loopback и `192.168.1.0/24`;
- не имеет directory listing;
- отдаёт только `latest.json`, `health.json` и текущий exact ZIP;
- запускается пользовательским LaunchAgent `com.fedorinov.owner-candidate-channel` после login/reboot;
- хранит generated channel state вне repository.

Canonical local root:

```text
~/Library/Application Support/FedorinovRewards/owner-candidate-channel
```

## Установка сервиса на Mac mini

```sh
python3 scripts/install_owner_candidate_channel_macos.py
```

Проверка:

```sh
launchctl print gui/$(id -u)/com.fedorinov.owner-candidate-channel
curl -fsS http://127.0.0.1:18387/health.json
curl -fsS http://Mac-mini-hermes.local:18387/latest.json
```

Rollback:

```sh
launchctl bootout gui/$(id -u) "$HOME/Library/LaunchAgents/com.fedorinov.owner-candidate-channel.plist"
```

После rollback файлы channel root можно сохранить для evidence или удалить отдельным явно подтверждённым cleanup. Production channel это не затрагивает.

## Публикация exact candidate

Использовать уже собранные ZIP и manifest; не пересобирать после acceptance:

```sh
python3 scripts/publish_owner_candidate_channel.py \
  --artifact dist/FedorinovRewards_WebPreview_vX.Y.Z.zip \
  --manifest dist/latest.json \
  --candidate-commit EXACT_ACCEPTED_FEATURE_OR_RELEASE_HEAD \
  --candidate-version X.Y.Z \
  --candidate-sha256 EXACT_SHA256 \
  --candidate-size EXACT_SIZE \
  --public-version CURRENT_PUBLIC_VERSION
```

Publisher проверяет accepted candidate commit/version, filename, package version, size, SHA256, source manifest и фактическую production version. Он не требует, чтобы candidate commit уже находился в `main`. Artifact записывается первым; `latest.json` атомарно заменяется последним. Любой mismatch останавливает публикацию до смены manifest.

## One-time physical bootstrap

Эту процедуру нельзя выполнять в обычной release-candidate stage. Нужна отдельная Owner authorization.

1. На permanent `Public Current` сохранить backup существующего `.env`.
2. Изменить только:

   ```text
   UPDATE_MANIFEST_URL=http://Mac-mini-hermes.local:18387/latest.json
   ```

3. Обычным `start_windows.bat` открыть текущую public version.
4. В «О программе» нажать «Проверить обновления» и подтвердить candidate version/SHA.
5. Не нажимать «Обновить», пока Owner не начинает manual acceptance.
6. При failure вернуть backup `.env`; DB/media и program files не изменяются.

После успешного bootstrap этот URL остаётся только в permanent Owner `Public Current`. Production installations Сергея продолжают использовать GitHub production channel.

## Release-candidate completion

До one-time bootstrap допустим только статус:

```text
REMOTE CHANNEL READY — ONE-TIME PHYSICAL BOOTSTRAP OWNER AUTHORIZATION REQUIRED
```

После bootstrap будущий RC может завершаться удалённо статусом:

```text
OWNER CANDIDATE CHANNEL READY — vX.Y.Z PUBLISHED FOR OWNER ONLY
```

Этот статус не означает merge в `main` или production publication. Следующий переход разрешён только после ручного Owner updater/product PASS.
