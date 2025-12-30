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

def setup_fifos():
    for pipe_name in ["snapfifo", "snapfifo_ledfx"]:
        path = f"/tmp/{pipe_name}"
        if not os.path.exists(path):
            log("INFO", f"📂 Creating Named Pipe at {path}")
            os.mkfifo(path)
        os.chmod(path, 0o666)

def setup_alsa_bridge(loopback_idx):
    log("INFO", f"🌉 Creating ALSA 44.1kHz Bridge on hw:{loopback_idx},1")
    config = f"""
pcm.!default {{
    type plug
    slave {{
        pcm "hw:{loopback_idx},1"
        rate 44100
        format S16_LE
        channels 2
    }}
}}
ctl.!default {{
    type hw
    card {loopback_idx}
}}
"""
    with open("/etc/asound.conf", "w") as f:
        f.write(config)

def list_alsa_devices():
    log("INFO", "🔍 Listing available ALSA devices:")
    try:
        result = subprocess.run(["aplay", "-L"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if any(x in line for x in ["hw:", "plughw:", "Loopback", "Pro", "default"]):
                print(f"    {line}")
    except Exception as e:
        log("WARN", f"Could not list ALSA devices: {e}")

def main():
    role = os.getenv("ROLE", "server").lower()
    
    host_raw = os.getenv("HOST", "").strip()
    host_uri = None
    if host_raw:
        host_uri = host_raw if "://" in host_raw else f"tcp://{host_raw}"
    
    loop_idx = os.getenv("LOOPBACK_NUMBER", "10")
    alsa_device = os.getenv("ALSA_DEVICE", "hw:0,0")
    client_id = os.getenv("CLIENT_ID", "")
    extra_args = os.getenv("EXTRA_ARGS", "").split()
    
    setup_system_services()

    if role == "server":
        log("INFO", "🚀 ROLE: SERVER")
        setup_fifos()
        config_file = "/config/snapserver.conf" if os.path.exists("/config/snapserver.conf") else "/etc/snapserver.conf"
        os.execv("/usr/bin/snapserver", ["snapserver", "-c", config_file] + extra_args)
    
    elif role == "client":
        log("INFO", f"🔈 ROLE: CLIENT (ALSA) ➡️ Target: {host_uri or 'Auto-Discovery'}")
        list_alsa_devices()
        
        cmd = ["snapclient", "--player", "alsa", "--soundcard", alsa_device]
        if client_id: cmd.extend(["--hostID", client_id])
        cmd.extend(extra_args)
        if host_uri: cmd.append(host_uri)
        
        os.execv("/usr/bin/snapclient", cmd)

    elif "ledfx" in role:
        log("INFO", f"💡 ROLE: LEDFX ONLY (Bridge: hw:{loop_idx})")
        setup_alsa_bridge(loop_idx)
        list_alsa_devices()
        
        ledfx_path = "/ledfx/venv/bin/ledfx"
        os.execv(ledfx_path, [ledfx_path, "--host", "0.0.0.0", "--port", "8888"])

if __name__ == "__main__":
    main()