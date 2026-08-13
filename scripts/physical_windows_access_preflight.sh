#!/bin/sh

set -eu

GATE_ALIAS=${FEDORINOV_GATE_ALIAS:-fedorinov-win-gate}
DISCOVERY_HELPER=${FEDORINOV_GATE_DISCOVERY_HELPER:-$HOME/.local/bin/fedorinov-win-gate-proxy}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WINDOWS_PREFLIGHT="$SCRIPT_DIR/windows/physical_access_preflight.ps1"

if [ ! -x "$DISCOVERY_HELPER" ]; then
    echo "FAIL: canonical discovery helper is unavailable" >&2
    exit 1
fi
if [ ! -r "$WINDOWS_PREFLIGHT" ]; then
    echo "FAIL: Windows access preflight script is unavailable" >&2
    exit 1
fi

discovery=$($DISCOVERY_HELPER --preflight 22)
printf '%s\n' "$discovery"

encoded_command=$(
    iconv -f UTF-8 -t UTF-16LE "$WINDOWS_PREFLIGHT" |
        base64 |
        tr -d '\n\r'
)
result=$(
    ssh -o BatchMode=yes -o ConnectTimeout=12 "$GATE_ALIAS" \
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded_command"
)
printf '%s\n' "$result"
