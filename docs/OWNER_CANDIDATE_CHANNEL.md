# Owner Candidate Channel

## Назначение

Physical Windows использует два независимых update channel:

- **Production channel** — public GitHub `latest.json`. Его используют Сергей и обычные production installations. Он меняется только в отдельно авторизованной publication stage.
- **Owner candidate channel** — private loopback channel только на physical test host. Он содержит exact непубликованный ZIP, уже прошедший Windows VM updater gate.

Candidate channel не является заменой VM gate. Это обязательный последний шаг release-candidate stage перед ручным Owner update.

## Постоянные пути

- Physical install: `C:\Users\codex\Desktop\Fedorinov Rewards - Public Current`
- Channel root: `C:\FedorinovGate\OwnerCandidateChannel`
- Manifest: `http://127.0.0.1:18387/latest.json`
- Scheduled Task: `FedorinovRewards-Owner-Candidate-Channel`
- Canonical SSH alias: `fedorinov-win-gate`

Сервер слушает только loopback. Candidate не публикуется в LAN, GitHub или production updater channel. Passwords/keys не хранятся в repo, command arguments, manifests или logs.

## Deploy после VM PASS

Использовать exact artifact, который прошёл VM gate. Не пересобирать его:

```sh
python3 scripts/prepare_owner_candidate_channel.py deploy \
  --artifact dist/FedorinovRewards_WebPreview_vX.Y.Z.zip \
  --manifest dist/latest.json \
  --candidate-commit FULL_MERGED_MAIN_SHA \
  --candidate-version X.Y.Z \
  --candidate-sha256 EXACT_SHA256 \
  --public-version CURRENT_PUBLIC_VERSION
```

Tool обязан остановиться до remote mutation, если расходятся:

- candidate commit/version;
- ZIP version/SHA;
- candidate manifest version/SHA;
- actual production manifest version;
- expected physical `Public Current` version.

На physical host deploy:

1. Проверяет product markers и version существующего `Public Current`.
2. Проверяет exact ZIP/manifest/SHA.
3. Атомарно заменяет только содержимое candidate channel.
4. Запускает/обновляет loopback Scheduled Task.
5. Проверяет channel health.
6. Меняет только `UPDATE_MANIFEST_URL` в `.env` существующей установки.
7. Сохраняет production URL в `channel-state.json` для restore.
8. Запускает canonical headed visibility gate и оставляет Edge на результате проверки.

DB/media paths, data fixture, launcher и product files не меняются. `Public Current` не копируется и не пересоздаётся.

## Обязательный physical visibility gate

После deploy:

1. Canonical physical discovery должен подтвердить host и interactive GUI session.
2. Остановить только stale task-owned candidate runtimes, если они мешают port/identity.
3. Запустить существующий `Public Current\start_windows.bat`.
4. Открыть видимый Edge через canonical physical GUI task.
5. Реальным click открыть `О программе → Проверить обновления`.
6. Подтвердить current version, candidate version, exact SHA и наличие формы update.
7. Подтвердить, что update progress не начат и installed version не изменилась.

Только затем допустим статус:

```text
READY FOR OWNER MANUAL PHYSICAL UPDATE: YES
```

Owner подходит к ноутбуку и сам нажимает `Обновить`. Codex не запускает update без отдельного разрешения.

## Status

```sh
python3 scripts/prepare_owner_candidate_channel.py status
```

PASS требует:

- installed physical version равна ожидаемой public baseline;
- `.env` указывает на loopback candidate manifest;
- Scheduled Task работает;
- listener принадлежит channel process;
- health version/SHA совпадают с exact candidate.

## Lifecycle

### Owner PASS

До publication вернуть physical install на production channel:

```sh
python3 scripts/prepare_owner_candidate_channel.py restore
```

После этого выполняется короткая publication stage из `docs/RELEASE_PROCESS.md`: exact parity, tag/GitHub Release, public `latest.json`, public byte/SHA verification и отдельно авторизованный Telegram. Уже принятые full/VM/physical gates повторять нельзя без evidence-based mismatch.

### Owner FAIL

Production channel не менять. После corrective merge/build/VM PASS повторный `deploy` заменяет только candidate channel и сохраняет permanent `Public Current`. Затем повторяется physical visibility gate нового exact candidate.

## Failure handling и rollback

- Если candidate server не стартовал, `.env` не переключается.
- Если порт занят процессом вне channel root, tool останавливается и не завершает этот процесс.
- Если physical updater не видит candidate, `READY` запрещён; production manifest не использовать как workaround.
- `restore` возвращает сохранённый canonical production URL, останавливает и удаляет только candidate Scheduled Task/listener.
- Если automatic restore невозможен, сравнить `channel-state.json`, `.env`, task/listener и остановиться. DB/media и product files не изменять.
