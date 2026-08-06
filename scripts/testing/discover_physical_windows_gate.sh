#!/bin/sh

set -eu

CONFIG_PATH="${FEDORINOV_GATE_CONFIG:-$HOME/.config/fedorinov-win-gate/discovery.env}"
KNOWN_HOSTS="${FEDORINOV_GATE_KNOWN_HOSTS:-$HOME/.ssh/known_hosts}"
CACHE_DIR="${FEDORINOV_GATE_CACHE_DIR:-$HOME/.cache/fedorinov-win-gate}"
CACHE_PATH="$CACHE_DIR/ip"

if [ ! -r "$CONFIG_PATH" ]; then
    echo "fedorinov-win-gate: missing discovery config: $CONFIG_PATH" >&2
    exit 255
fi

# The machine-local file contains infrastructure identity only; never credentials.
# shellcheck disable=SC1090
. "$CONFIG_PATH"

: "${GATE_HOST_KEY_ALIAS:?missing GATE_HOST_KEY_ALIAS}"
: "${GATE_MAC_PATTERN:?missing GATE_MAC_PATTERN}"
: "${GATE_INTERFACE:=en0}"
: "${GATE_MDNS_NAME:=}"

if [ "${1:-}" = "--discover" ]; then
    DISCOVERY_ONLY=1
    PORT="${2:-22}"
else
    DISCOVERY_ONLY=0
    PORT="${1:-22}"
fi

EXPECTED_KEY=$(
    /usr/bin/ssh-keygen -F "$GATE_HOST_KEY_ALIAS" -f "$KNOWN_HOSTS" 2>/dev/null |
        /usr/bin/awk '$2 == "ssh-ed25519" { print $3; exit }'
)
if [ -z "$EXPECTED_KEY" ]; then
    echo "fedorinov-win-gate: pinned ED25519 host key not found for $GATE_HOST_KEY_ALIAS" >&2
    exit 255
fi

is_ipv4() {
    printf '%s\n' "$1" | /usr/bin/grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$'
}

matches_host_key() {
    candidate=$1
    is_ipv4 "$candidate" || return 1
    scanned=$(
        /usr/bin/ssh-keyscan -T 2 -p "$PORT" -t ed25519 "$candidate" 2>/dev/null |
            /usr/bin/awk '$2 == "ssh-ed25519" { print $3; exit }'
    )
    [ -n "$scanned" ] && [ "$scanned" = "$EXPECTED_KEY" ]
}

remember_and_connect() {
    candidate=$1
    /bin/mkdir -p "$CACHE_DIR"
    /bin/chmod 700 "$CACHE_DIR"
    old_umask=$(umask)
    umask 077
    printf '%s\n' "$candidate" > "$CACHE_PATH"
    umask "$old_umask"
    if [ "$DISCOVERY_ONLY" -eq 1 ]; then
        printf '%s\n' "$candidate"
        exit 0
    fi
    exec /usr/bin/nc "$candidate" "$PORT"
}

try_candidate() {
    candidate=${1:-}
    [ -n "$candidate" ] || return 1
    if matches_host_key "$candidate"; then
        remember_and_connect "$candidate"
    fi
    return 1
}

if [ -r "$CACHE_PATH" ]; then
    try_candidate "$(/usr/bin/head -n 1 "$CACHE_PATH")" || true
fi

if [ -n "$GATE_MDNS_NAME" ]; then
    mdns_ip=$(
        /usr/bin/dscacheutil -q host -a name "$GATE_MDNS_NAME" 2>/dev/null |
            /usr/bin/awk '/ip_address:/ { print $2; exit }'
    )
    try_candidate "$mdns_ip" || true
fi

arp_ip=$(
    /usr/sbin/arp -a 2>/dev/null |
        /usr/bin/grep -Ei "$GATE_MAC_PATTERN" |
        /usr/bin/sed -E 's/.*\(([0-9.]+)\).*/\1/' |
        /usr/bin/head -n 1
)
try_candidate "$arp_ip" || true

local_ip=$(/usr/sbin/ipconfig getifaddr "$GATE_INTERFACE" 2>/dev/null || true)
if ! is_ipv4 "$local_ip"; then
    echo "fedorinov-win-gate: no IPv4 address on $GATE_INTERFACE" >&2
    exit 255
fi
prefix=${local_ip%.*}

scan_dir=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/fedorinov-win-gate.XXXXXX")
trap '/bin/rm -rf "$scan_dir"' EXIT HUP INT TERM

/usr/bin/seq 1 254 |
    /usr/bin/xargs -P 32 -I{} /bin/sh -c '
        ip="$1.$2"
        if /usr/bin/nc -G 1 -z "$ip" "$3" >/dev/null 2>&1; then
            printf "%s\n" "$ip"
        fi
    ' _ "$prefix" {} "$PORT" > "$scan_dir/open-ssh"

while IFS= read -r candidate; do
    try_candidate "$candidate" || true
done < "$scan_dir/open-ssh"

echo "fedorinov-win-gate: pinned physical host not found on $prefix.0/24" >&2
exit 255
