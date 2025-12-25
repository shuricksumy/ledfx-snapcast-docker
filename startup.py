#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from time import sleep

def log(level, msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def setup_system_services():
    """Start DBus and Avahi (required for discovery and some audio backends)."""
    log("INFO", "🔧 Initializing System Services (DBus/Avahi)")
    
    # Setup DBus
    Path("/run/dbus").mkdir(parents=True, exist_ok=True)
    if Path("/run/dbus/pid").exists(): Path("/run/dbus/pid").unlink()
    subprocess.run(["dbus-daemon", "--system", "--fork"], check=False)
    
    # Setup Avahi (Needs its own run directory)
    Path("/run/avahi-daemon").mkdir(parents=True, exist_ok=True)
    # Ensure permissions for the avahi user
    subprocess.run(["chown", "avahi:avahi", "/run/avahi-daemon"], check=False)
    
    subprocess.run(["avahi-daemon", "--daemonize"], check=False)
    sleep(0.5) # Short wait to let discovery settle

def main():
    role = os.getenv("ROLE", "server").lower()
    host = os.getenv("HOST", "localhost")
    backend = os.getenv("SOUND_BACKEND", "alsa").lower() 
    player_opts = os.getenv("PLAYER_OPTIONS", "")
    extra_args = (os.getenv("EXTRA_ARGS") or "").split()

    # Filter legacy Snapcast args to prevent crashes in v0.27+
    extra_args = [a for a in extra_args if not a.startswith(("--sound", "-s"))]

    if role == "server":
        setup_system_services()
        # Prioritize /config/snapserver.conf if volume-mounted
        cfg = Path("/config/snapserver.conf")
        if not cfg.exists():
            cfg = Path("/etc/snapserver.conf")
            
        log("INFO", f"🚀 ROLE: SERVER - Using config: {cfg}")
        os.execv("/usr/bin/snapserver", ["snapserver", "-c", str(cfg)] + extra_args)

    elif "ledfx" in role:
        setup_system_services()
        log("INFO", "💡 ROLE: LEDFX - Launching Visualizer and Client")
        
        # Start LedFx in background
        ledfx_bin = "/ledfx/venv/bin/ledfx" if Path("/ledfx/venv/bin/ledfx").exists() else "ledfx"
        subprocess.Popen([ledfx_bin, "--host", "0.0.0.0", "--port", "8888"])
        
        # LedFx Logic: ALSA needs Loopback
        if backend == "alsa" and "device=" not in player_opts:
            player_opts = "device=hw:Loopback,0,0"
        
        # --- FIX: Changed -p to --player ---
        p_arg = ["--player", f"{backend}:{player_opts}"] if player_opts else ["--player", backend]
        log("INFO", f"🔈 Starting client with backend: {backend}")
        os.execv("/usr/bin/snapclient", ["snapclient", "-h", host] + p_arg + extra_args)

    else:
        log("INFO", f"🔈 ROLE: CLIENT - Backend: {backend}")
        # --- FIX: Changed -p to --player ---
        p_arg = ["--player", f"{backend}:{player_opts}"] if player_opts else ["--player", backend]
        os.execv("/usr/bin/snapclient", ["snapclient", "-h", host] + p_arg + extra_args)

if __name__ == "__main__":
    main()