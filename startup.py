#!/usr/bin/env python3
import os, sys, subprocess, shutil
from pathlib import Path
from datetime import datetime
from time import sleep

def log(level, msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def setup_system_services():
    log("INFO", "🔧 Initializing DBus & Avahi")
    Path("/run/dbus").mkdir(parents=True, exist_ok=True)
    for p in ["/run/dbus/pid", "/run/dbus/system_bus_socket"]:
        if Path(p).exists(): Path(p).unlink()
    subprocess.run(["dbus-daemon", "--system", "--fork"], check=False)
    
    Path("/run/avahi-daemon").mkdir(parents=True, exist_ok=True)
    if Path("/run/avahi-daemon/pid").exists(): Path("/run/avahi-daemon/pid").unlink()
    subprocess.run(["chown", "avahi:avahi", "/run/avahi-daemon"], check=False)
    subprocess.run(["avahi-daemon", "--daemonize"], check=False)
    sleep(0.5)

def setup_pipewire():
    log("INFO", "🎸 Configuring PipeWire Context")
    Path("/etc/pipewire").mkdir(parents=True, exist_ok=True)
    Path("/run/user/1000").mkdir(parents=True, exist_ok=True)
    conf = Path("/etc/pipewire/client.conf")
    conf.write_text("context.modules = [ { name = libpipewire-module-protocol-native } { name = libpipewire-module-client-node } { name = libpipewire-module-adapter } ]\n")
    os.environ.update({
        "PIPEWIRE_RUNTIME_DIR": "/run/user/1000",
        "PIPEWIRE_REMOTE": "pipewire-0",
        "XDG_CONFIG_HOME": "/etc"
    })

def main():
    role = os.getenv("ROLE", "server").lower()
    host_raw = os.getenv("HOST", "localhost").strip()
    backend = os.getenv("SOUND_BACKEND", "alsa").lower() 
    player_opts = os.getenv("PLAYER_OPTIONS", "")
    
    setup_system_services()
    if backend == "pipewire": setup_pipewire()

    # --- URI AUTO-FIX ---
    host_uri = host_raw if "://" in host_raw else f"tcp://{host_raw}"

    if role == "server":
        cfg = Path("/config/snapserver.conf") if Path("/config/snapserver.conf").exists() else Path("/etc/snapserver.conf")
        log("INFO", f"🚀 SERVER STARTING: {cfg}")
        os.execv("/usr/bin/snapserver", ["snapserver", "-c", str(cfg)])
    else:
        if "ledfx" in role:
            log("INFO", "💡 LEDFX STARTING")
            subprocess.Popen(["ledfx", "--host", "0.0.0.0", "--port", "8888"])
        
        log("INFO", f"🔈 CLIENT STARTING: {backend} ➡️ {host_uri}")
        p_arg = ["--player", f"{backend}:{player_opts}"] if player_opts else ["--player", backend]
        os.execv("/usr/bin/snapclient", ["snapclient"] + p_arg + [host_uri])

if __name__ == "__main__":
    main()