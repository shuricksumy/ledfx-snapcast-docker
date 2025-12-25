#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from time import sleep

def log(level, msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def setup_system_services():
    """Start DBus and Avahi (required for discovery and PipeWire)."""
    log("INFO", "🔧 Initializing System Services (DBus/Avahi)")
    Path("/run/dbus").mkdir(parents=True, exist_ok=True)
    if Path("/run/dbus/pid").exists():
        Path("/run/dbus/pid").unlink()
    subprocess.run(["dbus-daemon", "--system", "--fork"], check=False)
    Path("/run/avahi-daemon").mkdir(parents=True, exist_ok=True)
    subprocess.run(["chown", "avahi:avahi", "/run/avahi-daemon"], check=False)
    subprocess.run(["avahi-daemon", "--daemonize"], check=False)
    sleep(0.3)

def main():
    role = os.getenv("ROLE", "server").lower()
    host_raw = os.getenv("HOST", "localhost").strip()
    backend = os.getenv("SOUND_BACKEND", "alsa").lower() 
    player_opts = os.getenv("PLAYER_OPTIONS", "")
    extra_args = (os.getenv("EXTRA_ARGS") or "").split()

    # Fix for Snapcast 0.27+ URI requirement
    if "://" not in host_raw:
        host_uri = f"tcp://{host_raw}"
    else:
        host_uri = host_raw

    # Filter out deprecated/fatal arguments
    extra_args = [a for a in extra_args if not a.startswith(("--sound", "-s", "-h", "--host", "--port"))]

    if role == "server":
        setup_system_services()
        cfg = Path("/config/snapserver.conf") if Path("/config/snapserver.conf").exists() else Path("/etc/snapserver.conf")
        log("INFO", f"🚀 ROLE: SERVER - Using config: {cfg}")
        os.execv("/usr/bin/snapserver", ["snapserver", "-c", str(cfg)] + extra_args)

    else:
        if "ledfx" in role:
            setup_system_services()
            log("INFO", "💡 ROLE: LEDFX - Launching Visualizer and Client")
            ledfx_bin = "/ledfx/venv/bin/ledfx" if Path("/ledfx/venv/bin/ledfx").exists() else shutil.which("ledfx")
            if ledfx_bin:
                subprocess.Popen([ledfx_bin, "--host", "0.0.0.0", "--port", "8888"])
            else:
                log("ERROR", "LedFx binary not found!")
            
            if backend == "alsa" and "device=" not in player_opts:
                player_opts = "device=hw:Loopback,0,0"

        log("INFO", f"🔈 ROLE: {role.upper()} - Backend: {backend} | URI: {host_uri}")
        p_arg = ["--player", f"{backend}:{player_opts}"] if player_opts else ["--player", backend]
        
        # Build final command with URI as last positional argument
        client_cmd = ["snapclient"] + p_arg + extra_args + [host_uri]
        os.execv("/usr/bin/snapclient", client_cmd)

if __name__ == "__main__":
    main()