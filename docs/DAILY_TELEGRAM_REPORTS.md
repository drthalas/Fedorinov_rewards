# Daily Telegram Reports

The project can send a daily Russian progress report for the project named "Награды и награждённые".

The report is intended to arrive every day at 09:00:

- Sergey receives the main report.
- Alexander receives a copy for quality control.
- Messages are sent by the existing colorizer/SAVBot Telegram bot from `~/Projects/picture-colorizer`.

## Safety Rules

- Do not send database contents, photos, media folders, backups, `.env` files, tokens, or generated local logs.
- Do not include personal records from the local application data.
- Do not commit Telegram tokens or real chat ids.
- Do not send a real message to Sergey until that first send is separately confirmed.

## Local Configuration

Copy the example file and edit only the local ignored file:

```sh
cp .env.daily-report.example .env.daily-report
```

Set recipients if automatic discovery is not desired:

```text
REPORT_PRIMARY_CHAT_ID=<telegram_user_id_Sergey>
REPORT_COPY_CHAT_IDS=<telegram_user_id_Alexander>
```

The bot token can be provided as:

```text
COLORIZER_BOT_TOKEN=<token>
```

In normal local use, leave `COLORIZER_BOT_TOKEN` empty. The sender reads the existing `TELEGRAM_BOT_TOKEN` from `~/Projects/picture-colorizer/.env` without printing it.

Before the first real daily send to Sergey, set this only after separate confirmation:

```text
REPORT_PRIMARY_SEND_CONFIRMED=true
```

## Dry Run

Preview the report without sending Telegram messages:

```sh
python3 scripts/send_daily_report.py --dry-run
```

Generate a report for a specific date:

```sh
python3 scripts/generate_daily_report.py --date YYYY-MM-DD
```

## Test Copy Only

After explicit confirmation, send one test message only to Alexander:

```sh
python3 scripts/send_daily_report.py --send-test-to-copy-only
```

This does not send a message to Sergey.

## Enable launchd

Copy the template:

```sh
cp deploy/launchd/com.fedorinov.daily-report.plist.example ~/Library/LaunchAgents/com.fedorinov.daily-report.plist
```

Load it:

```sh
launchctl load ~/Library/LaunchAgents/com.fedorinov.daily-report.plist
```

The template runs:

```sh
python3 scripts/send_daily_report.py
```

from:

```text
~/Projects/Fedorinov_Rewards/Fedorinov_rewards
```

at 09:00 every day.

## Disable launchd

```sh
launchctl unload ~/Library/LaunchAgents/com.fedorinov.daily-report.plist
```

## Logs

Send logs are written to:

```text
logs/daily_reports.jsonl
```

The `logs/` directory is ignored by Git. Logs contain status metadata and a report hash, not the Telegram token and not the full report text.
