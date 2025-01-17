#!/usr/bin/env python3

import os
import sys
import subprocess
import signal
from pathlib import Path
from time import sleep

def log_message(level, message):
    """Log messages with a timestamp and level."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}]  ➡️  {message}", flush=True)

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
    except subprocess.CalledProcessError as e:
        log_message("ERROR", f"Failed to start dbus-daemon: {e}")
    except Exception as e:
        log_message("ERROR", f"Unexpected error when starting dbus-daemon: {e}")

    try:
        log_message("INFO", "Starting avahi-daemon...")
        subprocess.Popen(["avahi-daemon", "--no-chroot"])
        log_message("INFO", "avahi-daemon started successfully.")
    except Exception as e:
        log_message("ERROR", f"Unexpected error when starting avahi-daemon: {e}")

    subprocess.run(["/usr/bin/snapserver", "-c", str(config_path)] + extra_args, check=True)

def start_client_mode(host, extra_args):
    log_message("INFO", "Starting in client mode...")
    subprocess.run(["/usr/bin/snapclient", "-h", host] + extra_args, check=True)

def start_ledfx_mode(host, extra_args):
    log_message("INFO", "Starting in client-ledfx mode...")
    log_message("INFO", "Run on host machine 'sudo modprobe snd-aloop'")

    def terminate_processes():
        """Terminate all running processes."""
        snapclient_proc.terminate()
        ledfx_proc.terminate()
        snapclient_proc.wait()
        ledfx_proc.wait()

    while True:
        # Start snapclient
        snapclient_proc = subprocess.Popen(["/usr/bin/snapclient", "-h", host] + extra_args)

        # Start ledfx
        ledfx_proc = subprocess.Popen(
            ["/ledfx/venv/bin/ledfx"],
            cwd="/ledfx",
            env=dict(os.environ, VIRTUAL_ENV="/ledfx/venv", PATH=f"/ledfx/venv/bin:{os.environ['PATH']}")
        )

        try:
            # Wait for any process to exit
            pid, _ = os.wait()
            if pid in (snapclient_proc.pid, ledfx_proc.pid):
                log_message("WARNING", "One of the processes has exited. Restarting both.")
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
        sleep(5)  # Timeout to avoid rapid restarts

def main():
    role = os.getenv("ROLE", "server")
    host = os.getenv("HOST", "localhost")
    extra_args = os.getenv("EXTRA_ARGS", "").split()

    if role == "server":
        start_server_mode(extra_args)
    elif role == "client":
        start_client_mode(host, extra_args)
    elif role == "ledfx":
        if not os.getenv("EXTRA_ARGS"):
            extra_args = ["--sound", "alsa", "--soundcard", "Loopback", "--hostID", "LedFX"]
            log_message("INFO", "Setting default EXTRA_ARGS for ledfx mode.")
        else:
            extra_args = os.getenv("EXTRA_ARGS").split()
        start_ledfx_mode(host, extra_args)
    else:
        log_message("ERROR", "Usage: ROLE={server|client|ledfx} [args]")
        sys.exit(1)

if __name__ == "__main__":
    main()
