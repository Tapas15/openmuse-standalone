# BrowserOS Docker Run Instructions

## Linux (recommended, GUI via noVNC + MCP)

### Prerequisites
- Docker Desktop running in **Linux containers** mode.
- Internet access during Docker build (default: auto-downloads BrowserOS Neo Linux installer from BrowserOS CDN).
- Optional: place a BrowserOS Linux installer in `./installer/` (`.deb` preferred; `.AppImage` supported) for local/offline build.

### Fresh start (clean machine / clean reset)
```powershell
cd <repo>
docker compose down -v --remove-orphans   # optional: removes old profile volume
docker compose up --build -d
```

### Access
- GUI (noVNC): http://localhost:6080
- Raw VNC: localhost:5900
- MCP: http://127.0.0.1:9010/mcp

### Verify MCP
```powershell
docker exec browseros-original python3 -c "import json,urllib.request; req=urllib.request.Request('http://127.0.0.1:9010/mcp',data=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'probe','version':'1'}}}).encode(),headers={'Content-Type':'application/json','Accept':'application/json, text/event-stream'}); r=urllib.request.urlopen(req,timeout=10); print(r.status)"
```
Expected: `200`.

### VS Code MCP
- Workspace config included: `.vscode/mcp.json` → `http://127.0.0.1:9010/mcp`.
- `Ctrl+Shift+P` → `MCP: List Servers` → Start/Restart `browseros`.
- If needed: `Developer: Reload Window`.

### Installer source options

- **Default (internet):** downloads `https://cdn.browseros.com/download/BrowserOS_neo.deb`.
- **Local installer:** put `.deb`/`.AppImage` in `./installer/`; local file is used first.
- **Override URL:**
  ```powershell
  $env:BROWSEROS_INSTALLER_URL="https://cdn.browseros.com/download/BrowserOS_neo.AppImage"
  docker compose up --build -d
  ```

### Fit / resize the BrowserOS screen

**File:** `docker-compose.yml` (env `RESOLUTION`, default `1600x900x24`).

Change size in `docker-compose.yml`:
```yaml
environment:
  RESOLUTION: "${RESOLUTION:-1366x768x24}"   # or 1600x900x24, 1920x1080x24
```

Or override without editing file:
```powershell
$env:RESOLUTION="1366x768x24"; docker compose up -d --force-recreate
```

Apply after change:
```powershell
docker compose up -d --force-recreate
```

noVNC fit tip: in the noVNC sidebar, set **Scaling Mode** to `Remote Resizing` or `Local Scaling`.

### Check status / logs
```powershell
docker compose ps
docker compose logs -f browseros
```

### Stop / start
```powershell
docker compose stop
docker compose start
```

### Remove / prune / reinstall

**Normal rebuild (keeps browser profile volume/data):**
```powershell
docker compose down
docker compose up --build -d
```

**Full reset for this project (removes containers, network, and `browseros-data` volume):**
```powershell
docker compose down -v --remove-orphans
docker compose up --build -d
```

**Remove this project's built image too (forces fresh image build):**
```powershell
docker compose down -v --remove-orphans --rmi local
docker compose up --build -d
```

**If you want Docker-wide cleanup (affects unused Docker resources, not just this project):**
```powershell
# Remove unused containers/networks/images/build cache
docker system prune -a

# Also remove unused volumes (DANGER: deletes unused Docker volumes)
docker system prune -a --volumes
```

Use `docker system prune ...` carefully; it can remove unrelated unused Docker data. For this repo only, prefer `docker compose down -v --remove-orphans --rmi local`.

### Data
- Persistent browser profile: Docker volume `browseros-data`.
- Host downloads folder mounted at `./downloads`.

## Notes
- Build auto-downloads BrowserOS Neo installer by default; local `./installer/` files take priority.
- Linux setup auto-selects `.deb` over `.AppImage` and skips `.exe`.
- Base image is `ubuntu:24.04` for GLIBC compatibility with BrowserOS Neo MCP sidecar.
- MCP is bridged internally (`socat` 9015/9016 -> 9010/9011) because BrowserOS MCP rejects non-loopback forwarded connections; host uses `127.0.0.1:9010/mcp`.
- See `changes_made__worked.md` for root causes, exact fixes, and scratch-install expectations.
