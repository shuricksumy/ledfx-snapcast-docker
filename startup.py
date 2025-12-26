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
    if Path("/run/avahi-daemon/pid").exists(): Path("/run/avahi-daemon/pid").unlink()
    subprocess.run(["avahi-daemon", "--daemonize"], check=False)

def setup_fifo():
    """Ensure the Named Pipe exists for the server stream"""
    fifo_path = "/tmp/snapfifo"
    if not os.path.exists(fifo_path):
        log("INFO", f"📂 Creating Named Pipe at {fifo_path}")
        os.mkfifo(fifo_path)
    os.chmod(fifo_path, 0o666)

def main():
    # Load Environment Variables
    role = os.getenv("ROLE", "server").lower()
    host_raw = os.getenv("HOST", "localhost").strip()
    alsa_device = os.getenv("ALSA_DEVICE", "hw:0,0")
    client_id = os.getenv("CLIENT_ID", "")
    extra_args = os.getenv("EXTRA_ARGS", "").split()
    
    setup_system_services()

    # Client Host Formatting
    host_uri = host_raw if "://" in host_raw else f"{host_raw}"

    if role == "server":
        log("INFO", "🚀 ROLE: SERVER (ALSA/Pipe Mode)")
        setup_fifo()
        
        # 📂 Logic: Use /config/snapserver.conf if it exists, otherwise use /etc/
        config_file = "/config/snapserver.conf"
        if not os.path.exists(config_file):
            log("INFO", f"⚠️  {config_file} not found. Falling back to /etc/snapserver.conf")
            config_file = "/etc/snapserver.conf"
        else:
            log("INFO", f"✅ Using custom config from {config_file}")

        cmd = ["snapserver", "-c", config_file] + extra_args
        os.execv("/usr/bin/snapserver", cmd)
    
    elif role == "client":
        log("INFO", f"🔈 ROLE: CLIENT (ALSA) ➡️ {host_uri}")
        
        cmd = ["snapclient", "--player", "alsa", "--soundcard", alsa_device, "-h", host_uri]
        if client_id:
            cmd.extend(["--hostID", client_id])
        cmd.extend(extra_args)
        
        os.execv("/usr/bin/snapclient", cmd)

    elif "ledfx" in role:
        log("INFO", f"💡 ROLE: LEDFX + CLIENT (Device: {alsa_device})")
        
        # Start LedFx with extra args
        ledfx_cmd = ["ledfx", "--host", "0.0.0.0", "--port", "8888"] + extra_args
        subprocess.Popen(ledfx_cmd)
        sleep(2)
        
        # Start Snapclient to feed LedFx
        log("INFO", f"🔈 Internal Snapclient feeding {alsa_device}")
        client_cmd = ["snapclient", "--player", "alsa", "--soundcard", alsa_device, "-h", host_uri]
        if client_id:
            client_cmd.extend(["--hostID", f"{client_id}-ledfx"])
            
        os.execv("/usr/bin/snapclient", client_cmd)

if __name__ == "__main__":
    main()