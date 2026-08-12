#!/bin/sh

set -eu

GATE_ALIAS=${FEDORINOV_GATE_ALIAS:-fedorinov-win-gate}
DISCOVERY_HELPER=${FEDORINOV_GATE_DISCOVERY_HELPER:-$HOME/.local/bin/fedorinov-win-gate-proxy}
KEYCHAIN_SERVICE=${FEDORINOV_GATE_KEYCHAIN_SERVICE:-fedorinov-win-gate}
KEYCHAIN_ACCOUNT=${FEDORINOV_GATE_KEYCHAIN_ACCOUNT:-codex}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WINDOWS_PREFLIGHT="$SCRIPT_DIR/windows/physical_gui_preflight.ps1"

if [ ! -x "$DISCOVERY_HELPER" ]; then
    echo "FAIL: canonical discovery helper is unavailable" >&2
    exit 1
fi

address=$($DISCOVERY_HELPER --discover 22)
if [ -z "$address" ]; then
    echo "FAIL: canonical discovery did not resolve the physical gate" >&2
    exit 1
fi

ssh -o BatchMode=yes -o ConnectTimeout=8 "$GATE_ALIAS" "cmd.exe /d /c echo ssh-ready" >/dev/null

if ! nc -G 3 -z "$address" 3389 >/dev/null 2>&1; then
    echo "FAIL: RDP listener is not reachable on the resolved trusted-LAN address" >&2
    exit 1
fi

if ! security find-generic-password \
    -a "$KEYCHAIN_ACCOUNT" \
    -s "$KEYCHAIN_SERVICE" >/dev/null 2>&1; then
    echo "FAIL: authorized RDP credential reference is absent from macOS Keychain" >&2
    exit 1
fi

encoded_command=$(
    iconv -f UTF-8 -t UTF-16LE "$WINDOWS_PREFLIGHT" |
        base64 |
        tr -d '\n\r'
)
result=$(
    ssh -o BatchMode=yes -o ConnectTimeout=8 "$GATE_ALIAS" \
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded_command" \
        2>/dev/null
)
if [ -z "$result" ]; then
    echo "FAIL: Windows interactive preflight returned no evidence" >&2
    exit 1
fi
if ! printf '%s\n' "$result" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
if payload.get("interactive_ready") is not True:
    raise SystemExit(1)
'; then
    echo "FAIL: Windows host is reachable but interactive desktop is unavailable" >&2
    printf '%s\n' "$result" >&2
    exit 1
fi
printf '%s\n' "$result"
