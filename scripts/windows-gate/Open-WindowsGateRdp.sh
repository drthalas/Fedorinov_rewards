#!/bin/sh
set -eu

host="${WINDOWS_GATE_RDP_HOST:-copew-04c68047f.local}"
server_name="${WINDOWS_GATE_RDP_SERVER_NAME:-copew-04c68047f}"
account="${WINDOWS_GATE_RDP_ACCOUNT:-codex}"
keychain_service="${WINDOWS_GATE_RDP_KEYCHAIN_SERVICE:-fedorinov-win-gate-rdp}"
certificate_sha256="${WINDOWS_GATE_RDP_CERTIFICATE_SHA256:-fb2dfc2d82b56a55dcb7206f7dd938046b1ca428f5525d57ed2fa4dc0571b834}"

client="${WINDOWS_GATE_RDP_CLIENT:-$(command -v sdl-freerdp || true)}"
if [ -z "$client" ] || [ ! -x "$client" ]; then
  printf '%s\n' "sdl-freerdp is required. Install Homebrew freerdp first." >&2
  exit 2
fi

credential="$(security find-generic-password \
  -a "$account" \
  -s "$keychain_service" \
  -w)"

if [ -z "$credential" ]; then
  printf '%s\n' "The Windows gate credential is missing from macOS Keychain." >&2
  exit 3
fi

# args-from keeps the credential out of the process command line.
printf '%s\n' \
  "/v:$host" \
  "/server-name:$server_name" \
  "/u:$account" \
  "/p:$credential" \
  "/cert:fingerprint:sha256:$certificate_sha256" \
  "+dynamic-resolution" \
  "+clipboard" \
  "/title:Fedorinov Windows Gate" |
  exec "$client" /args-from:stdin
