#!/usr/bin/env python3
import os, sys, subprocess
from pathlib import Path
from datetime import datetime
from time import sleep

def log(level, msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def setup_system_services():
    log("INFO", "🔧 Initializing D-Bus & Avahi")
    Path("/run/dbus").mkdir(parents=True, exist_ok=True)
    for p in ["/run/dbus/pid", "/run/dbus/system_bus_socket"]:
        if Path(p).exists(): Path(p).unlink()
    subprocess.run(["dbus-daemon", "--system", "--fork"], check=False)
    
    Path("/run/avahi-daemon").mkdir(parents=True, exist_ok=True)
    subprocess.run(["avahi-daemon", "--daemonize"], check=False)

def setup_fifo():
    fifo_path = "/tmp/snapfifo"
    if not os.path.exists(fifo_path):
        log("INFO", f"📂 Creating Named Pipe at {fifo_path}")
        os.mkfifo(fifo_path)
    os.chmod(fifo_path, 0o666)

def main():
    role = os.getenv("ROLE", "server").lower()
    host_raw = os.getenv("HOST", "localhost").strip()
    alsa_device = os.getenv("ALSA_DEVICE", "hw:0,0")
    
    setup_system_services()

    if role == "server":
        log("INFO", "🚀 ROLE: SERVER (Pipe Input for MA Controls)")
        setup_fifo()
        os.execv("/usr/bin/snapserver", ["snapserver", "-c", "/etc/snapserver.conf"])
    
    elif role == "client":
        log("INFO", f"🔈 ROLE: CLIENT (Direct ALSA) ➡️ {host_raw}")
        os.execv("/usr/bin/snapclient", ["snapclient", "--player", "alsa", "--soundcard", alsa_device, "-h", host_raw])

    elif "ledfx" in role:
        log("INFO", "💡 ROLE: LEDFX + CLIENT (Loopback Mode)")
        # Start LedFx 
        subprocess.Popen(["ledfx", "--host", "0.0.0.0", "--port", "8888"])
        sleep(3)
        # Snapclient outputs to the loopback (hw:10,0,0) so LedFx can capture it
        # hw:10 refers to the 'index=10' we set when loading the module
        log("INFO", f"🔈 Internal Snapclient playing to Loopback (hw:10,0,0)")
        os.execv("/usr/bin/snapclient", ["snapclient", "--player", "alsa", "--soundcard", "hw:10,0,0", "-h", host_raw])

if __name__ == "__main__":
    main()