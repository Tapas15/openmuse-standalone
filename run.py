#!/usr/bin/env python3
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / ".dev-pids.json"
LOG_DIR = ROOT / ".dev-logs"


def pnpm_cmd(*args):
    pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd") or "pnpm"
    if os.name == "nt" and pnpm.lower().endswith((".cmd", ".bat", ".ps1")):
        return [pnpm, *args]
    return [pnpm, *args]


def ensure_pnpm():
    """Ensure pnpm is available; try to enable/install via corepack if missing."""
    if shutil.which("pnpm") or shutil.which("pnpm.cmd"):
        return
    corepack = shutil.which("corepack") or shutil.which("corepack.cmd")
    if corepack:
        print("+ enabling pnpm via corepack", flush=True)
        try:
            subprocess.run([corepack, "enable"], cwd=ROOT, check=True, shell=(os.name == "nt"))
        except Exception:
            pass
        try:
            subprocess.run([corepack, "prepare", "pnpm@latest", "--activate"], cwd=ROOT, check=True, shell=(os.name == "nt"))
        except Exception:
            pass
    if not shutil.which("pnpm") and not shutil.which("pnpm.cmd"):
        raise SystemExit("pnpm is not installed. Install Node.js + pnpm (https://pnpm.io/installation), e.g. `corepack enable` then `corepack prepare pnpm@latest --activate`, or `npm i -g pnpm`.")


def base_env():
    env = os.environ.copy()
    # Let .env drive model/computer settings; stale shell env would override .env in server config.
    for k in (
        "COMPUTER_ENABLED",
        "COMPUTER_IMAGE",
        "COMPUTER_PROVIDER",
        "MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_CHAT_COMPLETIONS",
        "AGENT_BACKEND",
        "BROWSER_WORKER_URL",
    ):
        env.pop(k, None)
    return env


def env_file_value(key: str):
    path = ROOT / ".env"
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() != key:
            continue
        v = v.strip().strip('"').strip("'")
        return v
    return None


def tcp_ok(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def docker_container_status(name: str):
    docker = shutil.which("docker")
    if not docker:
        return None
    try:
        r = subprocess.run(
            [docker, "inspect", "-f", "{{.State.Status}}", name],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode != 0:
            return "not found"
        return (r.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def check_database(print_only: bool = True) -> bool:
    # Prefer explicit env, else .env value (server loads .env similarly for config).
    database_url = os.environ.get("DATABASE_URL") or env_file_value("DATABASE_URL")
    print("Database check:", flush=True)
    ok = True
    if database_url:
        parsed = urlparse(database_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 5432
        reachable = tcp_ok(host, port)
        status = "reachable" if reachable else "NOT reachable"
        print(f"  DATABASE_URL: set ({host}:{port}) -> {status}", flush=True)
        if not reachable:
            ok = False
            print("  Tip: start your Postgres and ensure DATABASE_URL is correct.", flush=True)
        # Helpful hint for the common local dev container.
        if "54329" in str(port) or "openmuse" in database_url:
            c = docker_container_status("openmuse-dev-db")
            if c:
                print(f"  Docker container openmuse-dev-db: {c}", flush=True)
                if c != "running":
                    print("  Tip: run `docker start openmuse-dev-db` (or `docker ps -a --filter name=openmuse-dev-db`).", flush=True)
    else:
        pglite = ROOT / ".openmuse" / "postgres"
        print(f"  DATABASE_URL: not set -> using embedded PGlite (local, no Docker) at {pglite}", flush=True)
        print("  Tip: to use local Docker Postgres set DATABASE_URL (e.g. postgres://openmuse:openmuse@127.0.0.1:54329/openmuse) and start container `openmuse-dev-db`.", flush=True)
    return ok


def run_install():
    print("+", " ".join(pnpm_cmd("install", "--frozen-lockfile")), flush=True)
    env = base_env()
    env["CI"] = "true"  # non-interactive install
    subprocess.run(pnpm_cmd("install", "--frozen-lockfile"), cwd=ROOT, env=env, check=True, shell=(os.name == "nt"))


def ensure_image_deps():
    """Ensure the sharp image-processing dependency is installed (used by /api/images auto-resize)."""
    try:
        subprocess.run(
            pnpm_cmd("ls", "sharp"),
            cwd=ROOT,
            capture_output=True,
            check=True,
            shell=(os.name == "nt"),
        )
        print("+ sharp already installed", flush=True)
        return
    except subprocess.CalledProcessError:
        pass
    print("+", " ".join(pnpm_cmd("add", "-w", "sharp")), flush=True)
    env = base_env()
    env["CI"] = "true"
    subprocess.run(pnpm_cmd("add", "-w", "sharp"), cwd=ROOT, env=env, check=True, shell=(os.name == "nt"))


def start_bg(name, script, env=None):
    LOG_DIR.mkdir(exist_ok=True)
    out = open(LOG_DIR / f"{name}.out.log", "a", encoding="utf-8", buffering=1)
    err = open(LOG_DIR / f"{name}.err.log", "a", encoding="utf-8", buffering=1)
    run_env = base_env() if env is None else env
    run_env.setdefault("CI", "true")
    cmd = pnpm_cmd(script)
    kwargs = {"cwd": ROOT, "env": run_env, "stdout": out, "stderr": err}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        kwargs["shell"] = True
    else:
        kwargs["start_new_session"] = True
    p = subprocess.Popen(cmd, **kwargs)
    print(f"started {name} pid={p.pid}", flush=True)
    return {"name": name, "pid": p.pid, "cmd": cmd, "proc": p}


def start_api():
    return start_bg("api", "dev")


def start_browser():
    env = base_env()
    # dev:browser loads .env via --env-file=.env; keep env minimal here.
    env.pop("CI", None)
    return start_bg("browser", "dev:browser", env=env)


def stop_proc(entry):
    if not entry:
        return
    proc = entry.get("proc")
    pid = entry.get("pid") or (proc.pid if proc else None)
    try:
        if os.name == "nt" and pid:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        elif proc:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        elif pid:
            os.kill(pid, 15)
    except Exception:
        pass


def stop_all(entries):
    for key in ("web", "browser", "api"):
        stop_proc(entries.get(key))
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


def kill_ports():
    """Kill processes listening on dev ports (8787, 8081, 8790)."""
    PORTS = [8787, 8081, 8790]
    if os.name == "nt":
        ports = ",".join(str(p) for p in PORTS)
        ps = (
            f"$ports=@({ports}); "
            "foreach($p in $ports){"
            "  Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | "
            "  ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } catch {} }"
            "}"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)
    else:
        for p in PORTS:
            try:
                out = subprocess.check_output(["lsof", "-ti", f"tcp:{p}"], text=True)
                for line in out.split():
                    kill_pid(int(line))
            except Exception:
                pass


def stop_existing_dev_processes():
    """Stop any previously started dev processes and free dev ports."""
    if PID_FILE.exists():
        try:
            data = json.loads(PID_FILE.read_text(encoding="utf-8"))
            for key in ("api", "web", "browser"):
                entry = data.get(key) or {}
                pid = entry.get("pid")
                if pid:
                    print(f"stopping existing {key} pid={pid}", flush=True)
                    stop_proc({"pid": pid})
        except Exception as e:
            print(f"warning: could not read pid file: {e}", file=sys.stderr)
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    kill_ports()


def main():
    if "--check-db" in sys.argv:
        ok = check_database()
        sys.exit(0 if ok else 1)

    ensure_pnpm()
    check_database()

    # Stop any previously running dev servers so ports are free.
    stop_existing_dev_processes()

    print("Installing dependencies (frontend + backend workspace)...", flush=True)
    run_install()
    ensure_image_deps()

    # Clear PGlite/embedded data dir on request to recover from local DB corruption (dev only).
    if os.environ.get("RESET_LOCAL_DB", "").lower() in ("1", "true", "yes"):
        db_dir = ROOT / ".openmuse" / "postgres"
        if db_dir.exists():
            backup = ROOT / ".openmuse" / f"postgres.bak-reset-{int(time.time())}"
            try:
                db_dir.rename(backup)
                print(f"Moved local DB to {backup}", flush=True)
            except Exception as e:
                print(f"Could not reset local DB: {e}", file=sys.stderr)

    procs = {}
    procs["api"] = start_api()
    procs["browser"] = start_browser()

    PID_FILE.write_text(
        json.dumps({k: {"name": v["name"], "pid": v["pid"], "cmd": v["cmd"]} for k, v in procs.items()}, indent=2),
        encoding="utf-8",
    )

    print("", flush=True)
    print("Dev servers starting (backend + browser worker + web).", flush=True)
    print("  API:     http://127.0.0.1:8787  (health: /api/health)", flush=True)
    print("  Browser: http://127.0.0.1:8790  (health: /health)", flush=True)
    print("  Web:     http://127.0.0.1:8081  (foreground: pnpm dev:web)", flush=True)
    print(f"  Logs:    {LOG_DIR}", flush=True)
    print("  Stop:    Ctrl+C or run 'python stop.py'", flush=True)
    print("  DB:      run `python run.py --check-db` to check database status only.", flush=True)
    print("Tip: if API crashes with PGlite/DB errors, stop and run with RESET_LOCAL_DB=1 (uses DATABASE_URL in .env if set).", flush=True)

    web_env = base_env()
    web_env.pop("CI", None)  # keep Expo watch/reload behavior
    web_cmd = pnpm_cmd("dev:web")
    print("+", " ".join(web_cmd), flush=True)

    def cleanup(*_):
        stop_all(procs)

    signal.signal(signal.SIGINT, lambda s, f: (cleanup(), sys.exit(130)))
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda s, f: (cleanup(), sys.exit(143)))

    try:
        rc = subprocess.run(web_cmd, cwd=ROOT, env=web_env, shell=(os.name == "nt")).returncode
        cleanup()
        sys.exit(rc)
    except KeyboardInterrupt:
        cleanup()
        sys.exit(130)
    finally:
        cleanup()


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(e.returncode)
