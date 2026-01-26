#!/usr/bin/env python3
import os, sys, subprocess, threading, time, shutil
from pathlib import Path
from datetime import datetime

def log(level, msg):
    """Internal supervisor logging."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def is_enabled(env_var, default=True):
    val = os.getenv(env_var, str(default)).lower()
    return val in ("true", "1", "yes", "on")

def show_config(file_path):
    """Prints the contents of a config file for debugging."""
    try:
        if os.path.exists(file_path):
            log("INFO", f"📄 Content of {file_path}:")
            print("-" * 40, flush=True)
            with open(file_path, "r") as f:
                content = f.read()
                print(content if content.strip() else "[Empty File]", flush=True)
            print("-" * 40, flush=True)
    except Exception: pass

def cleanup():
    """Safely removes stale locks and socket files."""
    log("INFO", "🧹 Performing pre-start cleanup...")
    paths = ["/tmp/.esd-*", "/tmp/pulse-*", "/var/run/dbus/pid"]
    for path_str in paths:
        try:
            base_dir = os.path.dirname(path_str)
            if os.path.exists(base_dir):
                for item in Path(base_dir).glob(os.path.basename(path_str)):
                    if item.is_file(): item.unlink()
                    elif item.is_dir(): shutil.rmtree(item)
        except Exception: pass

def setup_fifos():
    """Ensures Snapserver pipes exist."""
    for pipe_name in ["snapfifo", "snapfifo_ledfx"]:
        path = f"/tmp/{pipe_name}"
        try:
            if not os.path.exists(path):
                log("INFO", f"📂 Creating Named Pipe at {path}")
                os.mkfifo(path)
            os.chmod(path, 0o666)
        except Exception as e:
            log("ERROR", f"❌ Failed to setup FIFO {path}: {e}")

def stream_logs(process, prefix):
    """Managed logging for LedFx-Suite processes."""
    try:
        for line in iter(process.stdout.readline, ''):
            if line: print(f"[{prefix}] {line.strip()}", flush=True)
    except Exception: pass

def main():
    try:
        cleanup()
        
        role = os.getenv("ROLE", "ledfx-suite").lower()
        extra_args = [a for a in os.getenv("EXTRA_ARGS", "").split() if a]
        snap_host = os.getenv("SNAP_HOST", "127.0.0.1").strip()
        host_uri = snap_host if "://" in snap_host else f"tcp://{snap_host}"
        client_id = os.getenv("SNAP_CLIENT_ID", os.getenv("CLIENT_ID", "LedFx-Node"))

        log("INFO", f"🛠️ System initialized for Role: {role.upper()}")

        # --- ROLE: SNAPSERVER (Direct Execution) ---
        if role == "snapserver":
            setup_fifos()
            config_file = "/config/snapserver.conf" if os.path.exists("/config/snapserver.conf") else "/etc/snapserver.conf"
            show_config(config_file)
            log("INFO", "🚀 Handing over to Snapserver (PID 1)")
            # Replaces Python process with Snapserver
            os.execv("/usr/bin/snapserver", ["snapserver", "-c", config_file] + extra_args)

        # --- ROLE: SNAPCLIENT (Direct Execution) ---
        elif role == "snapclient":
            alsa_device = os.getenv("ALSA_DEVICE", "default")
            cmd_args = ["snapclient", "--player", "alsa", "--soundcard", alsa_device, "--hostID", client_id] + extra_args + [host_uri]
            log("INFO", f"🔈 Handing over to Snapclient (PID 1) on {alsa_device}")
            os.execv("/usr/bin/snapclient", cmd_args)

        # --- ROLE: LEDFX-SUITE (Managed Multi-process) ---
        elif role == "ledfx-suite":
            log("INFO", "🌈 Mode: LedFx Suite (Pulse Bridge)")
            subprocess.run(["pulseaudio", "--start", "--exit-idle-time=-1", "--disallow-exit"], check=False)
            with open("/etc/asound.conf", "w") as f:
                f.write('pcm.!default { type pulse }\nctl.!default { type pulse }')
            
            time.sleep(2)
            commands = {}
            if is_enabled("SNAPCLIENT_LEDFX_ENABLED"):
                commands["snapclient"] = ["snapclient", "--player", "alsa", "--soundcard", "default", "--hostID", client_id, host_uri]
            if is_enabled("SQUEEZELITE_LEDFX_ENABLED"):
                sq_cmd = ["squeezelite", "-o", "default", "-n", os.getenv("SQUEEZELITE_NAME", "LedFx")]
                if os.getenv("SQUEEZELITE_SERVER_PORT"): sq_cmd.extend(["-s", os.getenv("SQUEEZELITE_SERVER_PORT")])
                commands["squeezelite"] = sq_cmd
            
            commands["ledfx"] = ["/ledfx/venv/bin/ledfx", "--host", "0.0.0.0", "--port", "8888"]

            active_procs = []
            for name, cmd in commands.items():
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                threading.Thread(target=stream_logs, args=(p, name), daemon=True).start()
                active_procs.append(p)
            
            while True:
                for p in active_procs:
                    if p.poll() is not None: sys.exit(1)
                time.sleep(5)
        
        else:
            log("ERROR", f"Unknown Role: {role}")

    except Exception as e:
        log("ERROR", f"🛑 Global script crash: {e}")
        time.sleep(5)
        sys.exit(1)

if __name__ == "__main__":
    main()