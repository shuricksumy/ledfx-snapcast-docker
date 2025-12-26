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
    """Create dual pipes for Music (48k) and LedFx (44.1k)"""
    for pipe_name in ["snapfifo", "snapfifo_ledfx"]:
        path = f"/tmp/{pipe_name}"
        if not os.path.exists(path):
            log("INFO", f"📂 Creating Named Pipe at {path}")
            os.mkfifo(path)
        os.chmod(path, 0o666)

def setup_alsa_bridge(loopback_idx):
    """Forces LedFx container's default device to resample to 44.1kHz using specified loopback"""
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
    # Load Environment Variables
    role = os.getenv("ROLE", "server").lower()
    host_raw = os.getenv("HOST", "localhost").strip()
    clean_host = host_raw.replace("tcp://", "").replace("http://", "").split(":")[0]
    
    # Dynamic Loopback Number
    loop_idx = os.getenv("LOOPBACK_NUMBER", "10")
    
    # If role is ledfx, we force the alsa_device to the loopback input if not specified
    alsa_device = os.getenv("ALSA_DEVICE", f"hw:{loop_idx},0")
    
    client_id = os.getenv("CLIENT_ID", "")
    extra_args = os.getenv("EXTRA_ARGS", "").split()
    
    setup_system_services()

    if role == "server":
        log("INFO", "🚀 ROLE: SERVER (Dual Pipe Mode)")
        setup_fifos()
        config_file = "/config/snapserver.conf" if os.path.exists("/config/snapserver.conf") else "/etc/snapserver.conf"
        os.execv("/usr/bin/snapserver", ["snapserver", "-c", config_file] + extra_args)
    
    elif role == "client":
        log("INFO", f"🔈 ROLE: CLIENT (ALSA) ➡️ {clean_host}")
        list_alsa_devices()
        cmd = ["snapclient", "--player", "alsa", "--soundcard", alsa_device]
        if client_id: cmd.extend(["--hostID", client_id])
        cmd.extend(extra_args)
        cmd.append(clean_host)
        os.execv("/usr/bin/snapclient", cmd)

    elif "ledfx" in role:
        # 1. Get the loopback index (default to 10 if not set)
        loop_idx = os.getenv("LOOPBACK_NUMBER", "10")
        
        # 2. Define the specific ports for this virtual cable
        # Snapclient plays to port 0, LedFx listens to port 1
        playback_dev = f"hw:{loop_idx},0"
        capture_dev = f"hw:{loop_idx},1"

        log("INFO", f"💡 ROLE: LEDFX + CLIENT (Using Loopback {loop_idx})")
        
        # 3. Setup the resampling bridge for LedFx (Capture side)
        setup_alsa_bridge(loop_idx)
        list_alsa_devices()
        
        # 4. Start Snapclient feeding the playback side of the loopback
        log("INFO", f"🔈 Internal Snapclient feeding Loopback input: {playback_dev}")
        snap_cmd = ["snapclient", "--player", "alsa", "--soundcard", playback_dev]
        if client_id: 
            snap_cmd.extend(["--hostID", f"{client_id}-ledfx"])
        snap_cmd.append(clean_host)
        subprocess.Popen(snap_cmd)

        # 5. Wait for the 'wire' to go live
        log("INFO", f"⏳ Waiting for audio clock on card {loop_idx}...")
        hw_params_path = f"/proc/asound/card{loop_idx}/pcm0p/sub0/hw_params"
        
        for _ in range(20):
            if os.path.exists(hw_params_path):
                with open(hw_params_path, "r") as f:
                    if "closed" not in f.read():
                        log("INFO", "✅ Virtual cable active! Starting LedFx...")
                        break
            sleep(1)
        
        # 6. Launch LedFx
        ledfx_path = "/ledfx/venv/bin/ledfx"
        os.execv(ledfx_path, [ledfx_path, "--host", "0.0.0.0", "--port", "8888"] + extra_args)

if __name__ == "__main__":
    main()