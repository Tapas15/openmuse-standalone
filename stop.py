#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PID_FILE = ROOT / ".dev-pids.json"
PORTS = [8787, 8081, 8790]


def kill_pid(pid):
    if not pid:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(pid, 15)
    except Exception:
        pass


def kill_ports():
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


def main():
    if PID_FILE.exists():
        try:
            data = json.loads(PID_FILE.read_text(encoding="utf-8"))
            for key in ("api", "web", "browser"):
                entry = data.get(key) or {}
                pid = entry.get("pid")
                if pid:
                    print(f"stopping {key} pid={pid}")
                    kill_pid(pid)
        except Exception as e:
            print(f"warning: could not read pid file: {e}", file=sys.stderr)
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    else:
        print("No .dev-pids.json found; stopping listeners on dev ports (8787/8081/8790) if any.")

    kill_ports()
    print("Done.")


if __name__ == "__main__":
    main()
