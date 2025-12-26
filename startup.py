#!/usr/bin/env python3
import os, sys, subprocess, shutil
from pathlib import Path
from datetime import datetime
from time import sleep

def log(level, msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def setup_internal_audio():
    log("INFO", "🔊 Starting Standalone PipeWire Audio Stack")
    # Setup runtime env for root
    os.makedirs("/run/user/0", exist_ok=True)
    os.environ["XDG_RUNTIME_DIR"] = "/run/user/0"
    
    # 1. Start DBus (Mandatory for PipeWire/WirePlumber)
    Path("/run/dbus").mkdir(parents=True, exist_ok=True)
    if Path("/run/dbus/pid").exists(): Path("/run/dbus/pid").unlink()
    subprocess.run(["dbus-daemon", "--system", "--fork"], check=False)

    # 2. Start PipeWire Daemons
    subprocess.Popen(["pipewire"], stdout=subprocess.DEVNULL)
    sleep(1)
    subprocess.Popen(["wireplumber"], stdout=subprocess.DEVNULL)
    sleep(2) # Wait for USB scan

    # 3. Configure ALSA Bridge
    alsa_conf = Path("/etc/alsa/conf.d/99-pipewire-default.conf")
    alsa_conf.write_text('pcm.!default { type pipewire }\nctl.!default { type pipewire }\n')
    
    # 4. Set Environment for Snapclient
    os.environ.update({
        "PIPEWIRE_RUNTIME_DIR": "/run/user/0",
        "PIPEWIRE_REMOTE": "pipewire-0",
    })

def main():
    role = os.getenv("ROLE", "server").lower()
    host_raw = os.getenv("HOST", "localhost").strip()
    backend = os.getenv("SOUND_BACKEND", "pipewire").lower() 
    
    # Always setup audio stack if we are a client
    if role != "server":
        setup_internal_audio()

    # URI Fix
    host_uri = host_raw if "://" in host_raw else f"tcp://{host_raw}"

    if role == "server":
        log("INFO", "🚀 STARTING SERVER")
        os.execv("/usr/bin/snapserver", ["snapserver", "-c", "/etc/snapserver.conf"])
    else:
        if "ledfx" in role:
            log("INFO", "💡 STARTING LEDFX")
            subprocess.Popen(["ledfx", "--host", "0.0.0.0", "--port", "8888"])
        
        log("INFO", f"🔈 STARTING CLIENT: {backend} ➡️ {host_uri}")
        os.execv("/usr/bin/snapclient", ["snapclient", "--player", backend, host_uri])

if __name__ == "__main__":
    main()