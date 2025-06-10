#!/usr/bin/env python3

import os
import sys
import subprocess
import signal
from pathlib import Path
from time import sleep

def log_message(level, message):
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}]  ➡️  {message}", flush=True)

def detect_audio_backend():
    pulse_socket = Path(os.getenv("PULSE_SERVER", "/run/user/1000/pulse/native"))
    if pulse_socket.exists():
        return "pulse", "default"
    else:
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                if d['max_output_channels'] > 0:
                    return "alsa", d['name']
        except Exception:
            pass
    return None, None

def print_available_devices():
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        print("\nAvailable Audio Output Devices:")
        print("--------------------------------------------------")
        for idx, dev in enumerate(devices):
            if dev['max_output_channels'] > 0:
                print(f"[{idx}] {dev['name']} (host: {dev['hostapi']})")
        print("\nTo manually select a device, set:")
        print("  EXTRA_ARGS=\"--sound=alsa --soundcard='DEVICE_NAME_OR_INDEX'\"\n")
    except Exception as e:
        log_message("ERROR", f"Unable to list audio devices: {e}")

def start_server_mode(extra_args):
    log_message("INFO", "Starting in server mode...")

    config_path = Path("/config/snapserver.conf")
    if not config_path.exists():
        default_config = Path("/etc/snapserver.conf")
        config_path.write_text(default_config.read_text())
        log_message("INFO", "Default configuration copied to /config/snapserver.conf.")
    else:
        log_message("INFO", "Configuration file already exists in /config/snapserver.conf.")

    try:
        log_message("INFO", "Starting dbus-daemon...")
        if not Path("/run/dbus").exists():
            Path("/run/dbus").mkdir(parents=True, exist_ok=True)
        subprocess.run(["dbus-daemon", "--system"], check=True)
        log_message("INFO", "dbus-daemon started successfully.")
    except Exception as e:
        log_message("ERROR", f"DBus start error: {e}")

    try:
        log_message("INFO", "Starting avahi-daemon...")
        subprocess.Popen(["avahi-daemon", "--no-chroot"])
    except Exception as e:
        log_message("ERROR", f"Avahi start error: {e}")

    try:
        subprocess.run(["/usr/bin/snapserver", "-c", str(config_path)] + extra_args, check=True)
    except subprocess.CalledProcessError as e:
        log_message("ERROR", f"Snapserver failed to start: {e}")
        print_available_devices()

def start_client_mode(host, extra_args):
    log_message("INFO", f"Starting in client mode, host: {host}")
    try:
        subprocess.run(["/usr/bin/snapclient", "-h", host] + extra_args, check=True)
    except subprocess.CalledProcessError as e:
        log_message("ERROR", f"Snapclient failed to start: {e}")
        print_available_devices()

def start_ledfx_mode(host, extra_args):
    log_message("INFO", "Starting in client-ledfx mode...")
    log_message("INFO", "Run on host machine: sudo modprobe snd-aloop")

    def terminate_processes():
        snapclient_proc.terminate()
        ledfx_proc.terminate()
        snapclient_proc.wait()
        ledfx_proc.wait()

    while True:
        snapclient_proc = subprocess.Popen(["/usr/bin/snapclient", "-h", host] + extra_args)
        ledfx_proc = subprocess.Popen(
            ["/ledfx/venv/bin/ledfx"],
            cwd="/ledfx",
            env=dict(os.environ, VIRTUAL_ENV="/ledfx/venv", PATH=f"/ledfx/venv/bin:{os.environ['PATH']}")
        )

        try:
            pid, _ = os.wait()
            if pid in (snapclient_proc.pid, ledfx_proc.pid):
                log_message("WARNING", "One of the processes exited. Restarting both.")
                terminate_processes()
        except KeyboardInterrupt:
            log_message("INFO", "Interrupted. Stopping processes.")
            terminate_processes()
            break
        except Exception as e:
            log_message("ERROR", f"Unexpected error: {e}")
            terminate_processes()
            break

        log_message("INFO", "Restarting processes after 5 seconds...")
        sleep(5)

def main():
    role = os.getenv("ROLE", "server")
    host = os.getenv("HOST", "localhost")
    extra_args_env = os.getenv("EXTRA_ARGS", "")
    extra_args = extra_args_env.split() if extra_args_env else []

    # Auto-detect audio backend if not provided and we're in client mode
    if role in ("client", "ledfx") and not extra_args:
        backend, device = detect_audio_backend()
        if backend:
            extra_args = [f"--sound={backend}", f"--soundcard={device}", "--hostID=AutoClient"]
            log_message("INFO", f"Autodetected audio: backend={backend}, device={device}")
        else:
            log_message("WARNING", "No audio backend found. Snapclient may fail.")

    if role == "server":
        start_server_mode(extra_args)
    elif role == "client":
        start_client_mode(host, extra_args)
    elif role == "ledfx":
        start_ledfx_mode(host, extra_args)
    else:
        log_message("ERROR", "Invalid ROLE. Use ROLE=server|client|ledfx")
        sys.exit(1)

if __name__ == "__main__":
    main()