#!/usr/bin/env bash
set -euo pipefail

RESOLUTION="${RESOLUTION:-1600x900x24}"
DISPLAY="${DISPLAY:-:0}"
VNC_PORT="${VNC_PORT:-5900}"
NOVNC_PORT="${NOVNC_PORT:-6080}"
USER_HOME="${HOME:-/home/browser}"
USER_DATA_DIR="${USER_DATA_DIR:-$USER_HOME/data}"
RUN_AS_USER="${RUN_AS_USER:-browser}"

cleanup() {
  kill "${NOVNC_PID:-0}" "${VNC_PID:-0}" "${FLUXBOX_PID:-0}" "${XVFB_PID:-0}" "${SOCAT_MCP_PID:-0}" "${SOCAT_MCP2_PID:-0}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Persisted volume can keep stale Chromium singleton locks or wrong ownership.
mkdir -p "$USER_DATA_DIR" /downloads /tmp/.X11-unix
chown -R "$RUN_AS_USER:$RUN_AS_USER" "$USER_HOME" /downloads 2>/dev/null || true
rm -f "$USER_DATA_DIR"/SingletonLock "$USER_DATA_DIR"/SingletonCookie "$USER_DATA_DIR"/SingletonSocket \
      /tmp/.X0-lock /tmp/.X11-unix/X0 2>/dev/null || true

find_browseros_bin() {
  local candidates=(
    "${BROWSEROS_BIN:-}"
    "/usr/local/bin/browseros-app"
    "$(command -v browseros 2>/dev/null || true)"
    "$(command -v browserclaw 2>/dev/null || true)"
    "$(command -v BrowserOS 2>/dev/null || true)"
    "/usr/lib/browserclaw/browserclaw"
    "/opt/browseros/browseros"
  )

  local c
  for c in "${candidates[@]}"; do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return 0; }
  done

  # Last resort: search common locations, excluding installer/helper scripts.
  local found
  found="$(find /opt /usr/lib /usr/bin -type f -perm -111 \
    \( -iname '*browseros*' -o -iname '*browserclaw*' \) \
    ! -name 'install-browseros.sh' \
    ! -path '*/BrowserClawServer/*' \
    ! -path '*/browseros_extensions/*' 2>/dev/null | head -n1 || true)"
  [ -n "$found" ] && { echo "$found"; return 0; }
  return 1
}

Xvfb "$DISPLAY" -screen 0 "$RESOLUTION" -ac +extension GLX +render -noreset &
XVFB_PID=$!

for i in $(seq 1 50); do
  if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
  sleep 0.1
done

fluxbox >/tmp/fluxbox.log 2>&1 &
FLUXBOX_PID=$!

x11vnc -display "$DISPLAY" -forever -shared -rfbport "$VNC_PORT" -nopw -listen 0.0.0.0 >/tmp/x11vnc.log 2>&1 &
VNC_PID=$!

websockify --web=/usr/share/novnc "0.0.0.0:${NOVNC_PORT}" "localhost:${VNC_PORT}" >/tmp/novnc.log 2>&1 &
NOVNC_PID=$!

# BrowserOS MCP binds 0.0.0.0:9010 but rejects non-loopback connections; bridge it for Docker port publishing.
socat TCP-LISTEN:9015,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:9010 >/tmp/socat-mcp-9010.log 2>&1 &
SOCAT_MCP_PID=$!
socat TCP-LISTEN:9016,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:9011 >/tmp/socat-mcp-9011.log 2>&1 &
SOCAT_MCP2_PID=$!

echo "noVNC: http://localhost:${NOVNC_PORT}"
echo "VNC:   localhost:${VNC_PORT}"

BROWSER_BIN="$(find_browseros_bin || true)"
if [ -z "$BROWSER_BIN" ]; then
  echo "ERROR: BrowserOS binary not found. Check installer contents in ./installer/."
  echo "You can also set BROWSEROS_BIN=/path/to/binary in docker-compose.yml."
  exit 1
fi

echo "Launching: $BROWSER_BIN"
if [ "$(id -u)" = "0" ] && id "$RUN_AS_USER" >/dev/null 2>&1; then
  exec runuser -u "$RUN_AS_USER" -- "$BROWSER_BIN" \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --user-data-dir="$USER_DATA_DIR" \
    --no-first-run \
    "$@"
fi

exec "$BROWSER_BIN" \
  --no-sandbox \
  --disable-dev-shm-usage \
  --disable-gpu \
  --user-data-dir="$USER_DATA_DIR" \
  --no-first-run \
  "$@"