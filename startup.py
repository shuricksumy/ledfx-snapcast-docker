#!/usr/bin/env python3
import os, sys, subprocess, shutil
from pathlib import Path
from datetime import datetime
from time import sleep

def log(level, msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def setup_internal_audio():
    log("INFO", "🔊 Initializing Standalone Audio Stack (Root Mode)")
    
    # 1. Force the Runtime Directory
    runtime_dir = "/run/user/0"
    os.makedirs(runtime_dir, exist_ok=True)
    os.chmod(runtime_dir, 0o700)
    os.environ["XDG_RUNTIME_DIR"] = runtime_dir
    
    # 2. Start System DBus
    log("INFO", "🚌 Starting System DBus")
    os.makedirs("/run/dbus", exist_ok=True)
    if os.path.exists("/run/dbus/pid"): os.remove("/run/dbus/pid")
    subprocess.run(["dbus-daemon", "--system", "--fork"], check=False)
    sleep(1)

    # 3. Launch PipeWire & WirePlumber inside a DBus Session
    # This prevents the "$DISPLAY" and "Session Bus" errors
    log("INFO", "🎸 Launching PipeWire + WirePlumber")
    
    # Use 'dbus-run-session' to create a temporary bus for PipeWire to use
    pw_cmd = "dbus-run-session -- pipewire & sleep 2 && wireplumber &"
    subprocess.Popen(["bash", "-c", pw_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    sleep(4) # Give WirePlumber enough time to find the Topping DX3

    # 4. Final ALSA Bridge
    log("INFO", "🌉 Bridging ALSA to PipeWire")
    os.makedirs("/etc/alsa/conf.d", exist_ok=True)
    with open("/etc/alsa/conf.d/99-pipewire-default.conf", "w") as f:
        f.write('pcm.!default { type pipewire }\nctl.!default { type pipewire }\n')

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