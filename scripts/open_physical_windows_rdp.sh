#!/bin/sh

set -eu

DISCOVERY_HELPER=${FEDORINOV_GATE_DISCOVERY_HELPER:-$HOME/.local/bin/fedorinov-win-gate-proxy}
KEYCHAIN_SERVICE=${FEDORINOV_GATE_KEYCHAIN_SERVICE:-fedorinov-win-gate}
KEYCHAIN_ACCOUNT=${FEDORINOV_GATE_KEYCHAIN_ACCOUNT:-codex}
RDP_CLIENT=${FEDORINOV_GATE_RDP_CLIENT:-$(command -v sdl-freerdp || true)}

if [ ! -x "$DISCOVERY_HELPER" ]; then
    echo "FAIL: canonical discovery helper is unavailable" >&2
    exit 1
fi
if [ -z "$RDP_CLIENT" ] || [ ! -x "$RDP_CLIENT" ]; then
    echo "FAIL: sdl-freerdp is unavailable" >&2
    exit 1
fi

address=$($DISCOVERY_HELPER --discover 22)
if [ -z "$address" ]; then
    echo "FAIL: canonical discovery did not resolve the physical gate" >&2
    exit 1
fi

security find-generic-password \
    -a "$KEYCHAIN_ACCOUNT" \
    -s "$KEYCHAIN_SERVICE" \
    -w |
    "$RDP_CLIENT" \
        "/v:$address" \
        "/u:$KEYCHAIN_ACCOUNT" \
        /from-stdin:force \
        /cert:tofu \
        /dynamic-resolution \
        /w:1440 \
        /h:900 \
        /title:Fedorinov-Physical-Windows-Gate \
        /clipboard \
        /audio-mode:2 \
        /log-level:WARN
