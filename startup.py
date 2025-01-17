#!/usr/bin/env python3

import os
import sys
import subprocess
import signal
from pathlib import Path
from time import sleep

def start_server_mode(extra_args):
    print("[Startup ➡️ ] Starting in server mode...", flush=True)

    config_path = Path("/config/snapserver.conf")
    if not config_path.exists():
        default_config = Path("/etc/snapserver.conf")
        config_path.write_text(default_config.read_text())
        print("[Startup ➡️ ] Default configuration copied to /config/snapserver.conf.", flush=True)
    else:
        print("[Startup ➡️ ] Configuration file already exists in /config/snapserver.conf.", flush=True)

    subprocess.run(["dbus-daemon", "--system"], check=True)
    subprocess.Popen(["avahi-daemon", "--no-chroot"])
    subprocess.run(["/usr/bin/snapserver", "-c", str(config_path)] + extra_args, check=True)

def start_client_mode(host, extra_args):
    print("[Startup ➡️ ] Starting in client mode...", flush=True)
    subprocess.run(["/usr/bin/snapclient", "-h", host] + extra_args, check=True)

def start_ledfx_mode(host, extra_args):
    print("[Startup ➡️ ] Starting in client-ledfx mode...", flush=True)
    print("[Startup ➡️ ] Run on host machine 'sudo modprobe snd-aloop'", flush=True)

    if not extra_args:
        extra_args = ["--sound", "alsa", "--soundcard", "Loopback", "--hostID", "LedFX"]
        print(f"[Startup ➡️ ] Setting default EXTRA_ARGS: {' '.join(extra_args)}", flush=True)
    else:
        print(f"[Startup ➡️ ] EXTRA_ARGS is set as: {' '.join(extra_args)}", flush=True)

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
            while True:
                pid, _ = os.wait()
                if pid in (snapclient_proc.pid, ledfx_proc.pid):
                    print("[Startup ➡️ ] One of the processes has exited. Stopping both.", flush=True)
                    snapclient_proc.terminate()
                    ledfx_proc.terminate()
                    break
        except KeyboardInterrupt:
            print("[Startup ➡️ ] Interrupted. Stopping processes.", flush=True)
            snapclient_proc.terminate()
            ledfx_proc.terminate()

        snapclient_proc.wait()
        ledfx_proc.wait()

        print("[Startup ➡️ ] Restarting processes after 5 seconds...", flush=True)
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
        extra_args = os.getenv("EXTRA_ARGS", "--sound alsa --soundcard Loopback --hostID LedFX").split()
        start_ledfx_mode(host, extra_args)
    else:
        print("[Startup ➡️ ] Usage: ROLE={server|client|ledfx} [args]", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
