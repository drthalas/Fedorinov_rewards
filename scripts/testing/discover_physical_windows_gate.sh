#!/bin/sh

set -eu

# Preserve the ProxyCommand transport before candidate loops redirect stdin.
exec 3<&0

CONFIG_PATH="${FEDORINOV_GATE_CONFIG:-$HOME/.config/fedorinov-win-gate/discovery.env}"
KNOWN_HOSTS="${FEDORINOV_GATE_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
CACHE_DIR="${FEDORINOV_GATE_CACHE_DIR:-$HOME/.cache/fedorinov-win-gate}"
CACHE_PATH="$CACHE_DIR/ip"
STATUS_PATH="$CACHE_DIR/status.json"

if [ ! -r "$CONFIG_PATH" ]; then
    echo "fedorinov-win-gate: missing machine-local discovery config" >&2
    exit 255
fi

# Machine-local infrastructure identity only. Credentials never belong here.
# shellcheck disable=SC1090
. "$CONFIG_PATH"

: "${GATE_HOST_KEY_ALIAS:?missing GATE_HOST_KEY_ALIAS}"
: "${GATE_MAC_PATTERN:?missing GATE_MAC_PATTERN}"
: "${GATE_MDNS_NAME:=}"
: "${GATE_INTERFACE:=}"

MODE=connect
PORT=22
case "${1:-}" in
    --discover)
        MODE=discover
        PORT="${2:-22}"
        ;;
    --preflight)
        MODE=preflight
        PORT="${2:-22}"
        ;;
    "") ;;
    *) PORT=$1 ;;
esac

EXPECTED_KEY=$(
    /usr/bin/ssh-keygen -F "$GATE_HOST_KEY_ALIAS" -f "$KNOWN_HOSTS" 2>/dev/null |
        /usr/bin/awk '$2 == "ssh-ed25519" { print $3; exit }'
)
if [ -z "$EXPECTED_KEY" ]; then
    echo "fedorinov-win-gate: pinned ED25519 host key is unavailable" >&2
    exit 255
fi

is_ipv4() {
    printf '%s\n' "$1" | /usr/bin/grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$'
}

active_interface() {
    if [ -n "$GATE_INTERFACE" ] && /usr/sbin/ipconfig getifaddr "$GATE_INTERFACE" >/dev/null 2>&1; then
        printf '%s\n' "$GATE_INTERFACE"
        return
    fi
    /sbin/route -n get default 2>/dev/null |
        /usr/bin/awk '/interface:/ { print $2; exit }'
}

json_status() {
    state=$1
    source=${2:-none}
    address=${3:-}
    detail=${4:-}
    /bin/mkdir -p "$CACHE_DIR"
    /bin/chmod 700 "$CACHE_DIR"
    old_umask=$(umask)
    umask 077
    STATE="$state" SOURCE="$source" ADDRESS="$address" DETAIL="$detail" \
        /usr/bin/python3 -c '
import datetime
import json
import os

print(json.dumps({
    "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "state": os.environ["STATE"],
    "source": os.environ["SOURCE"],
    "address": os.environ["ADDRESS"],
    "detail": os.environ["DETAIL"],
}, separators=(",", ":")))
' > "$STATUS_PATH"
    umask "$old_umask"
}

remember_address() {
    address=$1
    /bin/mkdir -p "$CACHE_DIR"
    /bin/chmod 700 "$CACHE_DIR"
    old_umask=$(umask)
    umask 077
    printf '%s\n' "$address" > "$CACHE_PATH"
    umask "$old_umask"
}

tcp_open() {
    /usr/bin/nc -G 2 -z "$1" "$2" >/dev/null 2>&1
}

ssh_banner() {
    banner=$(
        (/usr/bin/nc -G 3 -w 3 "$1" "$PORT" 2>/dev/null || true) |
            /usr/bin/head -n 1
    )
    printf '%s\n' "$banner" | /usr/bin/grep -Eq '^SSH-[0-9]'
}

scanned_key() {
    /usr/bin/ssh-keyscan -T 3 -p "$PORT" -t ed25519 "$1" 2>/dev/null |
        /usr/bin/awk '$2 == "ssh-ed25519" { print $3; exit }'
}

append_candidate() {
    address=${1:-}
    source=${2:-unknown}
    is_ipv4 "$address" || return 0
    if ! /usr/bin/grep -Fq "|$address|" "$CANDIDATES" 2>/dev/null; then
        printf '|%s|%s|\n' "$address" "$source" >> "$CANDIDATES"
    fi
}

populate_arp() {
    prefix=$1
    /usr/bin/seq 1 254 |
        /usr/bin/xargs -P 32 -I{} /bin/sh -c \
            '/sbin/ping -q -c 1 -W 250 "$1.$2" >/dev/null 2>&1 || true' _ "$prefix" {}
}

emit_failure() {
    state=$1
    source=${2:-none}
    address=${3:-}
    detail=${4:-}
    json_status "$state" "$source" "$address" "$detail"
    echo "fedorinov-win-gate: $state${detail:+ ($detail)}" >&2
    exit 255
}

scan_dir=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/fedorinov-win-gate.XXXXXX")
trap '/bin/rm -rf "$scan_dir"' EXIT HUP INT TERM
CANDIDATES="$scan_dir/candidates"
: > "$CANDIDATES"

reachable_seen=0
port_seen=0
banner_timeout_seen=0
key_mismatch_seen=0
inspect_candidates() {
    while IFS='|' read -r _ address source _; do
        [ -n "$address" ] || continue
        if [ "$source" = "arp-scan" ] || /sbin/ping -q -c 1 -W 1000 "$address" >/dev/null 2>&1; then
            reachable_seen=1
        fi
        if ! tcp_open "$address" "$PORT"; then
            continue
        fi
        port_seen=1
        if ! ssh_banner "$address"; then
            banner_timeout_seen=1
            continue
        fi
        actual_key=$(scanned_key "$address")
        if [ -z "$actual_key" ]; then
            banner_timeout_seen=1
            continue
        fi
        if [ "$actual_key" != "$EXPECTED_KEY" ]; then
            key_mismatch_seen=1
            continue
        fi

        remember_address "$address"
        rdp_state=unavailable
        if tcp_open "$address" 3389; then
            rdp_state=reachable
        fi
        json_status SSH_READY "$source" "$address" "rdp=$rdp_state"
        case "$MODE" in
            discover) printf '%s\n' "$address"; exit 0 ;;
            preflight) cat "$STATUS_PATH"; exit 0 ;;
            connect) exec /usr/bin/nc "$address" "$PORT" <&3 ;;
        esac
    done < "$CANDIDATES"
}

if [ -r "$CACHE_PATH" ]; then
    cached_address=$(/usr/bin/head -n 1 "$CACHE_PATH")
    if [ "$MODE" = "connect" ] && is_ipv4 "$cached_address" && tcp_open "$cached_address" "$PORT"; then
        # ProxyCommand must not pre-open banner/keyscan sessions for every SSH
        # command. The outer OpenSSH process enforces StrictHostKeyChecking and
        # HostKeyAlias on this transport; explicit discovery keeps the richer
        # banner/key failure classification below.
        exec /usr/bin/nc "$cached_address" "$PORT" <&3
    fi
    append_candidate "$cached_address" cache
    inspect_candidates
    : > "$CANDIDATES"
fi

if [ -n "$GATE_MDNS_NAME" ]; then
    /usr/bin/dscacheutil -q host -a name "$GATE_MDNS_NAME" 2>/dev/null |
        /usr/bin/awk '/ip_address:/ { print $2 }' > "$scan_dir/mdns-addresses"
    while IFS= read -r address; do
        append_candidate "$address" mdns
    done < "$scan_dir/mdns-addresses"
fi

interface=$(active_interface)
if [ -z "$interface" ]; then
    emit_failure LOCAL_LAN_UNAVAILABLE none "" "no active IPv4 interface"
fi
local_ip=$(/usr/sbin/ipconfig getifaddr "$interface" 2>/dev/null || true)
if ! is_ipv4 "$local_ip"; then
    emit_failure LOCAL_LAN_UNAVAILABLE none "" "active interface has no IPv4"
fi
prefix=${local_ip%.*}

arp_address=$(
    /usr/sbin/arp -a 2>/dev/null |
        /usr/bin/grep -Ei "$GATE_MAC_PATTERN" |
        /usr/bin/sed -E 's/.*\(([0-9.]+)\).*/\1/' |
        /usr/bin/head -n 1
)
append_candidate "$arp_address" arp

# mDNS and the current ARP table are the second bounded discovery tier.
inspect_candidates
: > "$CANDIDATES"

# Populate ARP independently of TCP/22. This lets preflight distinguish a
# reachable host with broken sshd from a host that is absent from the LAN.
populate_arp "$prefix"
arp_address=$(
    /usr/sbin/arp -a 2>/dev/null |
        /usr/bin/grep -Ei "$GATE_MAC_PATTERN" |
        /usr/bin/sed -E 's/.*\(([0-9.]+)\).*/\1/' |
        /usr/bin/head -n 1
)
append_candidate "$arp_address" arp-scan
inspect_candidates

if [ "$key_mismatch_seen" -eq 1 ]; then
    emit_failure HOST_KEY_MISMATCH candidate "" "SSH banner answered with an untrusted key"
fi
if [ "$banner_timeout_seen" -eq 1 ]; then
    emit_failure SSH_BANNER_TIMEOUT candidate "" "TCP/22 accepted but SSH identity was not returned"
fi
if [ "$port_seen" -eq 0 ] && [ "$reachable_seen" -eq 1 ]; then
    emit_failure HOST_REACHABLE_SSHD_UNAVAILABLE candidate "" "host answers on LAN but TCP/22 is unavailable"
fi
emit_failure HOST_NOT_FOUND none "" "canonical identity not present on active trusted subnet"
