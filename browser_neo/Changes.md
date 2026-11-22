# BrowserOS Docker + MCP — Changes Made (Working)

## Status

Working as of 2026-11-21 in this repo.

- Container: `browseros-original` running on Ubuntu 24.04 base image.
- GUI: `http://localhost:6080` (noVNC), `localhost:5900` (raw VNC).
- MCP: `http://127.0.0.1:9010/mcp` returns MCP initialize success (`serverInfo.name=browseros-neo`).
- Verified: BrowserOS MCP navigation/search worked (opened Google and searched "lion").
- Installer: **no local installer required**; build auto-downloads BrowserOS Neo Linux x64 from BrowserOS CDN by default. Local `./installer/` files are optional and take priority.

## Problems Found

1. **MCP sidecar failed on Debian bookworm (GLIBC too old).**
   - `browseros-claw-server` required `GLIBC_2.38/2.39`; Debian bookworm provided 2.36.
   - Logs showed repeated: `browseros: Every server installation failed; retrying in 30s`.
   - Symptom: port 9010 listened but `/mcp` returned `503 Service Unavailable`.

2. **Ubuntu 24.04 package name change.**
   - `libasound2` is not installable directly on Ubuntu 24.04; `libasound2t64` is required.

3. **MCP port not exposed by Docker.**
   - Original compose exposed only `5900/6080`; MCP `9010/9011` were container-internal.

4. **Docker-published MCP connections were reset by BrowserOS MCP.**
   - Inside container, `POST http://127.0.0.1:9010/mcp` worked (`200`, SSE MCP response).
   - From Windows host through Docker port publish, connection was closed/reset (`ECONNRESET` / empty reply).
   - Fix: bridge host-facing ports to loopback MCP via `socat`.

5. **Stale Chromium profile singleton lock after rebuild/restart.**
   - Persisted `browseros-data` volume kept `SingletonLock/Cookie/Socket`; BrowserOS exited with profile singleton errors and container restart-looped.
   - Fix: clean stale lock files on startup and ensure profile ownership.

6. **Local installer dependency.**
   - Originally required `./installer/BrowserOS_neo.deb` or `.AppImage`.
   - Fix: `install-browseros.sh` now downloads from BrowserOS CDN when no supported local installer is present. Defaults:
     - `BROWSEROS_INSTALLER_URL=https://cdn.browseros.com/download/BrowserOS_neo.deb`
     - `BROWSEROS_APPIMAGE_URL=https://cdn.browseros.com/download/BrowserOS_neo.AppImage`

## Exact Changes

### `Dockerfile`

- Base image: `FROM debian:bookworm-slim` → `FROM ubuntu:24.04`.
- Package: `libasound2` → `libasound2t64`.
- Added package: `socat` (MCP loopback bridge).
- Added build args/env for installer download URLs (`BROWSEROS_INSTALLER_URL`, `BROWSEROS_APPIMAGE_URL`).
- Final user: `USER $USER` → `USER root` so entrypoint can clean stale locks/fix ownership, then drop to `browser`.

### `docker-compose.yml`

- Added build args with default CDN URLs for auto-download.

- Added MCP port mappings:
  - `127.0.0.1:9010:9015` — BrowserOS MCP bridged endpoint
  - `127.0.0.1:9011:9016` — secondary MCP bridged endpoint
- Kept existing noVNC/VNC mappings: `6080`, `5900`.
- Kept persistent volume `browseros-data:/home/browser/data` and `./downloads:/downloads`.

### `install-browseros.sh`

- Keeps local-installer-first behavior for `./installer/` (`.deb` preferred, `.AppImage` supported, `.exe` ignored).
- If no local supported installer exists, downloads from `BROWSEROS_INSTALLER_URL` (default BrowserOS CDN `.deb`).
- Uses `curl -fsSL --retry 3 --retry-delay 2`.

### `start.sh`

- Added `USER_DATA_DIR` and `RUN_AS_USER`.
- Startup cleanup/ownership:
  - `mkdir -p "$USER_DATA_DIR" /downloads /tmp/.X11-unix`
  - `chown -R "$RUN_AS_USER:$RUN_AS_USER" "$USER_HOME" /downloads`
  - remove stale locks: `SingletonLock`, `SingletonCookie`, `SingletonSocket`, `/tmp/.X0-lock`, `/tmp/.X11-unix/X0`
- Added MCP bridges (because BrowserOS MCP rejects non-loopback forwarded connections):
  - `socat TCP-LISTEN:9015,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:9010`
  - `socat TCP-LISTEN:9016,fork,reuseaddr,bind=0.0.0.0 TCP:127.0.0.1:9011`
- Added socat PIDs to cleanup trap.
- Launch BrowserOS as `browser` via `runuser` when container starts as root; use `--user-data-dir="$USER_DATA_DIR"`.

### VS Code MCP config (machine/user setting, outside repo)

Updated local VS Code user MCP config to use working endpoint:

- File: `C:\Users\Tapas\AppData\Roaming\Code\User\mcp.json`
- `browseros` and `browseros-neo` set to `http://127.0.0.1:9010/mcp`.

Workspace convenience config added:

- `.vscode/mcp.json` points to `http://127.0.0.1:9010/mcp`.

> Note: VS Code/Kilo MCP client config is per-user/per-workspace depending on where you put it. The Docker repo itself cannot force another machine's global VS Code settings.

## Fresh Install / Scratch Setup

These repo changes make the Docker image/container reproducible. On a clean machine:

### Prerequisites

- Docker Desktop installed and running (Linux containers mode).
- Internet access for Docker build (to download BrowserOS installer from CDN), unless you provide a local installer in `./installer/`.

### Start from scratch

```powershell
cd <repo>
docker compose down -v --remove-orphans
docker compose up --build -d
```

### Remove / prune / reinstall

```powershell
# Normal rebuild (keep profile data)
docker compose down
docker compose up --build -d

# Full project reset (removes containers/network/browseros-data volume)
docker compose down -v --remove-orphans
docker compose up --build -d

# Full project reset + remove local project image
docker compose down -v --remove-orphans --rmi local
docker compose up --build -d

# Docker-wide cleanup (careful: affects unused Docker resources globally)
docker system prune -a
docker system prune -a --volumes   # DANGER: removes unused volumes
```

Prefer project-scoped `docker compose down ...` for this repo; use `system prune` only when you intentionally want global Docker cleanup.

### Verify

```powershell
docker compose ps
docker compose logs --tail 80 browseros
```

MCP probe:

```powershell
docker exec browseros-original python3 -c "import json,urllib.request; req=urllib.request.Request('http://127.0.0.1:9010/mcp',data=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'probe','version':'1'}}}).encode(),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}); r=urllib.request.urlopen(req,timeout=10); print(r.status)"
```

Expected: `200`.

GUI: open `http://localhost:6080`.

## MCP Client Setup (one-time per client/profile)

The container exposes MCP at `http://127.0.0.1:9010/mcp`. Configure your MCP client to that URL.

### VS Code

- Workspace config: `.vscode/mcp.json` (included).
- Or user config: `%APPDATA%\Code\User\mcp.json`.
- After config/container start: `Ctrl+Shift+P` → `MCP: List Servers` → Start/Restart `browseros`. Reload window if needed.

### Kilo

Kilo global config example (`~/.config/kilo/kilo.jsonc` or `%USERPROFILE%\.config\kilo\kilo.jsonc`):

```jsonc
{
  "mcp": {
    "browseros": {
      "type": "remote",
      "url": "http://127.0.0.1:9010/mcp",
      "enabled": true,
      "timeout": 15000
    }
  }
}
```

## Will it work from scratch?

**Docker/container: yes, with this repo as-is.** On a clean machine with Docker Desktop (Linux containers) and internet access, `docker compose up --build -d` should build and run without manual container tweaks. It auto-downloads the BrowserOS Neo Linux installer from BrowserOS CDN; local `./installer/` files are optional overrides.

**MCP client: one-time config per client/profile.** Point the client at `http://127.0.0.1:9010/mcp`. VS Code workspace is covered by `.vscode/mcp.json`; other clients/profiles need their own MCP entry once.

**Caveats:** Docker Desktop must be installed/running; build needs internet unless a local installer is supplied; corporate proxy/firewall can block CDN download; BrowserOS CDN URLs/version behavior may change upstream. If MCP breaks after an installer upgrade, recheck container logs and the 9010/9015 probes documented above.