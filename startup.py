#!/usr/bin/env python3

import os
import sys
import subprocess
from pathlib import Path
from time import sleep

def log(level, msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

def print_aplay_devices():
    log("INFO", "🔊 Available ALSA Devices (aplay -L):")
    try:
        result = subprocess.run(["aplay", "-L"], capture_output=True, text=True, check=True)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        log("ERROR", f"Failed to run aplay -L: {e}")

def resolve_alsa_device(device_name_hint):
    try:
        result = subprocess.run(["aplay", "-L"], capture_output=True, text=True, check=True)
        lines = result.stdout.splitlines()
        for i in range(len(lines) - 1):
            if lines[i].startswith(("plughw:", "hw:")):
                description = lines[i + 1].lower()
                if device_name_hint.lower() in description:
                    log("INFO", f"Resolved device '{device_name_hint}' to: {lines[i]}")
                    return lines[i].strip()
    except Exception as e:
        log("ERROR", f"Failed to resolve ALSA device: {e}")
    return None

def auto_detect_backend():
    pulse_socket = Path(os.getenv("PULSE_SERVER", "/run/user/1000/pulse/native"))
    return "pulse" if pulse_socket.exists() else "alsa"

def start_snapclient(host, extra_args):
    log("INFO", f"Starting snapclient for host {host} with args: {' '.join(extra_args)}")
    try:
        subprocess.run(["/usr/bin/snapclient", "-h", host] + extra_args, check=True)
    except subprocess.CalledProcessError as e:
        log("ERROR", f"Snapclient failed to start: {e}")
        print_aplay_devices()

def start_server(extra_args):
    log("INFO", "Starting Snapserver (server mode)")
    config_path = Path("/config/snapserver.conf")
    if not config_path.exists():
        default = Path("/etc/snapserver.conf")
        config_path.write_text(default.read_text())
        log("INFO", "Copied default config to /config/")

    try:
        if not Path("/run/dbus").exists():
            Path("/run/dbus").mkdir(parents=True, exist_ok=True)

        result = subprocess.run(["pgrep", "dbus-daemon"], capture_output=True, text=True)
        if result.returncode != 0:
            pid_path = Path("/run/dbus/pid")
            if pid_path.exists():
                log("WARNING", "Removing stale /run/dbus/pid")
                pid_path.unlink()
            subprocess.run(["dbus-daemon", "--system"], check=True)
            log("INFO", "Started dbus-daemon")
        else:
            log("INFO", "dbus-daemon already running")
    except Exception as e:
        log("ERROR", f"Error while checking/starting dbus-daemon: {e}")

    try:
        subprocess.Popen(["avahi-daemon", "--no-chroot"])
        log("INFO", "Started avahi-daemon")
    except Exception as e:
        log("ERROR", f"Error while starting avahi-daemon: {e}")

    try:
        subprocess.run(["/usr/bin/snapserver", "-c", str(config_path)] + extra_args, check=True)
    except Exception as e:
        log("ERROR", f"Snapserver error: {e}")
        print_aplay_devices()

def start_ledfx_client(host, extra_args):
    log("INFO", "Starting snapclient + LedFx mode")
    def terminate(p1, p2):
        p1.terminate(); p2.terminate()
        p1.wait(); p2.wait()

    while True:
        snap_proc = subprocess.Popen(["/usr/bin/snapclient", "-h", host] + extra_args)
        ledfx_proc = subprocess.Popen(
            ["/ledfx/venv/bin/ledfx"],
            cwd="/ledfx",
            env={**os.environ, "VIRTUAL_ENV": "/ledfx/venv", "PATH": f"/ledfx/venv/bin:{os.environ['PATH']}"}
        )
        try:
            pid, _ = os.wait()
            if pid in (snap_proc.pid, ledfx_proc.pid):
                log("WARNING", "Process exited, restarting...")
                terminate(snap_proc, ledfx_proc)
        except KeyboardInterrupt:
            log("INFO", "Interrupted by user")
            terminate(snap_proc, ledfx_proc)
            break
        except Exception as e:
            log("ERROR", f"Unexpected error: {e}")
            terminate(snap_proc, ledfx_proc)
            break
        sleep(5)

def start_ledfx_only():
    log("INFO", "Starting LedFx in standalone mode")
    try:
        subprocess.run(
            ["/ledfx/venv/bin/ledfx"],
            cwd="/ledfx",
            env={**os.environ, "VIRTUAL_ENV": "/ledfx/venv", "PATH": f"/ledfx/venv/bin:{os.environ['PATH']}"}
        )
    except Exception as e:
        log("ERROR", f"LedFx failed to start: {e}")

def main():
    role = os.getenv("ROLE", "server").lower()
    host = os.getenv("HOST", "localhost")
    device_hint = os.getenv("DEVICE_NAME")
    sound_backend = os.getenv("SOUND_BACKEND", "").lower()
    client_id = os.getenv("CLIENT_ID")
    extra_args_env = os.getenv("EXTRA_ARGS", "")
    extra_args = extra_args_env.split() if extra_args_env else []

    print_aplay_devices()

    if role in ("client", "ledfx_client"):
        backend = None

        if sound_backend in ("alsa", "pulse"):
            backend = sound_backend
            log("INFO", f"Using SOUND_BACKEND override: {backend}")
        else:
            backend = auto_detect_backend()
            log("INFO", f"Auto-detected audio backend: {backend}")

        soundcard = None
        if not any(arg.startswith("--soundcard") for arg in extra_args):
            if backend == "alsa" and device_hint:
                soundcard = resolve_alsa_device(device_hint)
            elif backend == "pulse":
                soundcard = "default"

        if not any(arg.startswith("--sound=") for arg in extra_args):
            extra_args.append(f"--sound={backend}")

        if soundcard and not any(arg.startswith("--soundcard=") for arg in extra_args):
            extra_args.append(f"--soundcard={soundcard}")

        if not any(arg.startswith("--hostID=") for arg in extra_args):
            if client_id:
                extra_args.append(f"--hostID={client_id}")
                log("INFO", f"Using CLIENT_ID override: {client_id}")
            else:
                extra_args.append("--hostID=AutoClient")

        log("INFO", f"Final EXTRA_ARGS: {' '.join(extra_args)}")

    if role == "server":
        start_server(extra_args)
    elif role == "client":
        start_snapclient(host, extra_args)
    elif role == "ledfx_client":
        start_ledfx_client(host, extra_args)
    elif role == "ledfx":
        start_ledfx_only()
    else:
        log("ERROR", f"Invalid ROLE: {role}")
        sys.exit(1)

if __name__ == "__main__":
    main()
