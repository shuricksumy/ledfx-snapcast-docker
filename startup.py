#!/usr/bin/env python3
import os, sys, subprocess, threading, time, shutil
from pathlib import Path
from datetime import datetime

INIT_DELAY    = 5
MAX_DELAY     = 60
STABLE_RUN_S  = 30   # ran longer than this → reset backoff on next crash

def log(level, msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def is_enabled(env_var, default=True):
    return os.getenv(env_var, str(default)).lower() in ("true", "1", "yes", "on")

def show_config(file_path):
    try:
        if os.path.exists(file_path):
            log("INFO", f"📄 Content of {file_path}:")
            print("-" * 40, flush=True)
            with open(file_path) as f:
                content = f.read()
                print(content if content.strip() else "[Empty File]", flush=True)
            print("-" * 40, flush=True)
    except Exception:
        pass

def cleanup():
    log("INFO", "🧹 Performing pre-start cleanup...")
    paths = ["/tmp/.esd-*", "/tmp/pulse-*", "/var/run/dbus/pid", "/tmp/supervisor_health"]
    for path_str in paths:
        try:
            base_dir = os.path.dirname(path_str)
            if os.path.exists(base_dir):
                for item in Path(base_dir).glob(os.path.basename(path_str)):
                    if item.is_file(): item.unlink()
                    elif item.is_dir(): shutil.rmtree(item)
        except Exception:
            pass

def setup_fifos():
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
    try:
        for line in iter(process.stdout.readline, ''):
            if line:
                print(f"[{prefix}] {line.strip()}", flush=True)
    except Exception:
        pass

def start_process(name, cmd):
    log("INFO", f"🚀 Starting {name}: {' '.join(cmd)}")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    threading.Thread(target=stream_logs, args=(p, name), daemon=True).start()
    return p

def update_health():
    Path("/tmp/supervisor_health").touch()

def main():
    try:
        cleanup()

        role       = os.getenv("ROLE", "ledfx-suite").lower()
        extra_args = [a for a in os.getenv("EXTRA_ARGS", "").split() if a]
        snap_host  = os.getenv("SNAP_HOST", "127.0.0.1").strip()
        host_uri   = snap_host if "://" in snap_host else f"tcp://{snap_host}"
        client_id  = os.getenv("SNAP_CLIENT_ID", os.getenv("CLIENT_ID", "LedFx-Node"))

        log("INFO", f"🛠️ System initialized for Role: {role.upper()}")

        commands = {}

        if role == "snapserver":
            setup_fifos()
            config_file = "/config/snapserver.conf" if os.path.exists("/config/snapserver.conf") else "/etc/snapserver.conf"
            show_config(config_file)
            commands["snapserver"] = ["snapserver", "-c", config_file] + extra_args

        elif role == "snapclient":
            alsa_device = os.getenv("ALSA_DEVICE", "default")
            commands["snapclient"] = ["snapclient", "--player", "alsa", "--soundcard", alsa_device, "--hostID", client_id] + extra_args + [host_uri]

        elif role == "ledfx-suite":
            log("INFO", "🌈 Mode: LedFx Suite (Pulse Bridge)")
            subprocess.run(["pulseaudio", "--start", "--exit-idle-time=-1", "--disallow-exit"], check=False)
            with open("/etc/asound.conf", "w") as f:
                f.write('pcm.!default { type pulse }\nctl.!default { type pulse }')

            delay = int(os.getenv("STARTUP_DELAY_SEC", "2"))
            if delay > 0:
                log("INFO", f"⏱️ Waiting {delay}s for system readiness...")
                time.sleep(delay)

            if is_enabled("SNAPCLIENT_LEDFX_ENABLED"):
                commands["snapclient"] = ["snapclient", "--player", "pulse", "--soundcard", "default", "--hostID", client_id, host_uri]

            if is_enabled("SQUEEZELITE_LEDFX_ENABLED"):
                sq_cmd = ["squeezelite", "-o", "pulse", "-n", os.getenv("SQUEEZELITE_NAME", "LedFx")]
                if os.getenv("SQUEEZELITE_SERVER_PORT"): sq_cmd.extend(["-s", os.getenv("SQUEEZELITE_SERVER_PORT")])
                if os.getenv("SQUEEZELITE_MAC"):         sq_cmd.extend(["-m", os.getenv("SQUEEZELITE_MAC")])
                sq_extra = os.getenv("SQUEEZELITE_EXTRA_ARGS", "").split()
                if sq_extra: sq_cmd.extend(sq_extra)
                commands["squeezelite"] = sq_cmd

            commands["ledfx"] = ["/ledfx/venv/bin/ledfx", "--host", "0.0.0.0", "--port", "8888"]

        else:
            log("ERROR", f"Unknown Role: {role}")
            sys.exit(1)

        # --- LAUNCH ---
        active_procs = {name: start_process(name, cmd) for name, cmd in commands.items()}

        # Per-service backoff state
        # restart_at=None means the process is running (nothing scheduled)
        svc_state = {
            name: {"delay": INIT_DELAY, "restart_at": None, "started_at": time.monotonic()}
            for name in commands
        }

        log("INFO", "✅ All services running. Monitoring for crashes...")

        while True:
            update_health()
            now = time.monotonic()

            for name, p in list(active_procs.items()):
                state = svc_state[name]
                rc    = p.poll()

                if rc is None:
                    # Still running — reset backoff once it's been stable long enough
                    if (now - state["started_at"]) > STABLE_RUN_S:
                        state["delay"] = INIT_DELAY
                    continue

                # --- Process has exited ---
                if state["restart_at"] is None:
                    # First tick after exit — schedule restart
                    run_time = now - state["started_at"]
                    if run_time > STABLE_RUN_S:
                        state["delay"] = INIT_DELAY  # stable run → reset before scheduling
                    log("WARN", f"⚠️ '{name}' exited (code {rc}, ran {run_time:.0f}s). "
                                f"Restarting in {state['delay']}s...")
                    state["restart_at"] = now + state["delay"]
                    state["delay"] = min(state["delay"] * 2, MAX_DELAY)

                elif now >= state["restart_at"]:
                    # Backoff elapsed — restart
                    active_procs[name]   = start_process(name, commands[name])
                    state["restart_at"]  = None
                    state["started_at"]  = time.monotonic()

            time.sleep(2)

    except Exception as e:
        log("ERROR", f"🛑 Global script crash: {e}")
        time.sleep(5)
        sys.exit(1)

if __name__ == "__main__":
    main()
