#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
from time import sleep

# ------------------------ logging ------------------------
def log(level, msg):
    from datetime import datetime
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{level}]  ➡️  {msg}", flush=True)

# ------------------------ ALSA helpers ------------------------
def print_aplay_devices():
    log("INFO", "🔊 ALSA devices (aplay -L):")
    try:
        out = subprocess.run(["aplay", "-L"], capture_output=True, text=True, check=True).stdout
        print(out)
    except Exception as e:
        log("ERROR", f"aplay -L failed: {e}")

def resolve_alsa_device(device_name_hint: str | None) -> str | None:
    """Find an ALSA hw/plughw device matching the given name hint."""
    if not device_name_hint:
        return None
    try:
        out = subprocess.run(["aplay", "-L"], capture_output=True, text=True, check=True).stdout
        lines = out.splitlines()
        for i in range(len(lines) - 1):
            if lines[i].startswith(("plughw:", "hw:")):
                desc = lines[i + 1].lower()
                if device_name_hint.lower() in desc:
                    cand = lines[i].strip()
                    log("INFO", f"Resolved '{device_name_hint}' -> {cand}")
                    return cand
    except Exception as e:
        log("ERROR", f"Device resolve failed: {e}")
    return None

def ensure_loopback(index=10) -> bool:
    """Load snd-aloop for loopback playback/monitoring."""
    try:
        out = subprocess.check_output(["aplay", "-l"], text=True)
        if "Loopback" in out:
            log("INFO", "Loopback already present")
            return True
        log("INFO", f"Loading snd-aloop index={index}")
        subprocess.run(["modprobe", "snd-aloop", f"index={index}"], check=True)
        sleep(1.5)
        out = subprocess.check_output(["aplay", "-l"], text=True)
        ok = "Loopback" in out
        log("INFO" if ok else "ERROR", "Loopback ready" if ok else "Loopback missing")
        return ok
    except Exception as e:
        log("ERROR", f"Loopback setup failed: {e}")
        return False

# ------------------------ runner helpers ------------------------
def build_player_arg(opts: str | None) -> list[str]:
    arg = "alsa" if not opts else f"alsa:{opts}"
    return ["--player", arg]

def start_snapclient(host: str, args: list[str]):
    log("INFO", f"Starting snapclient for {host} with args: {' '.join(args)}")
    try:
        subprocess.run(["/usr/bin/snapclient", "-h", host] + args, check=True)
    except subprocess.CalledProcessError as e:
        log("ERROR", f"snapclient exited with code {e.returncode}")
        print_aplay_devices()

def start_server(args: list[str]):
    log("INFO", "Starting snapserver (server mode)")
    cfg = Path("/config/snapserver.conf")
    if not cfg.exists():
        default = Path("/etc/snapserver.conf")
        cfg.write_text(default.read_text())
        log("INFO", "Copied default snapserver.conf to /config")

    try:
        Path("/run/dbus").mkdir(parents=True, exist_ok=True)
        if subprocess.run(["pgrep", "dbus-daemon"], capture_output=True).returncode != 0:
            pid_path = Path("/run/dbus/pid")
            if pid_path.exists():
                pid_path.unlink(missing_ok=True)
            subprocess.run(["dbus-daemon", "--system"], check=True)
            log("INFO", "dbus-daemon started")
    except Exception as e:
        log("WARNING", f"dbus setup issue: {e}")

    try:
        subprocess.Popen(["avahi-daemon", "--no-chroot"])
        log("INFO", "avahi-daemon started")
    except Exception as e:
        log("WARNING", f"avahi start issue: {e}")

    try:
        subprocess.run(["/usr/bin/snapserver", "-c", str(cfg)] + args, check=True)
    except Exception as e:
        log("ERROR", f"snapserver error: {e}")

# ------------------------ main ------------------------
def main():
    role = os.getenv("ROLE", "server").lower()            # server | client
    host = os.getenv("HOST", "localhost")
    client_id = os.getenv("CLIENT_ID")                    # --hostID value
    device_hint = os.getenv("DEVICE_NAME")                # e.g. "usb dac"
    loopback = os.getenv("LOOPBACK", "0") == "1"          # set to 1 to use snd-aloop
    loopback_index = int(os.getenv("LOOPBACK_INDEX", "10"))

    # ALSA player options (example: buffer_time=100,fragments=4,device=plughw:1,0)
    player_opts = (os.getenv("PLAYER_OPTIONS") or "").strip()
    extra_args = (os.getenv("EXTRA_ARGS") or "").split()

    print_aplay_devices()

    # Loopback mode
    if loopback:
        if ensure_loopback(loopback_index):
            if "device=" not in player_opts:
                player_opts = (player_opts + "," if player_opts else "") + f"device=plughw:{loopback_index},0"
        else:
            log("FATAL", "LOOPBACK=1 but snd-aloop unavailable")
            sys.exit(1)
    else:
        if device_hint and "device=" not in player_opts:
            resolved = resolve_alsa_device(device_hint)
            if resolved:
                player_opts = (player_opts + "," if player_opts else "") + f"device={resolved}"

    player_arg = build_player_arg(player_opts)

    if client_id and role == "client":
        extra_args.append(f"--hostID={client_id}")

    log("INFO", f"ALSA player options: {player_opts}")
    log("INFO", f"Final args: {' '.join(player_arg + extra_args)}")

    if role == "server":
        start_server(extra_args)
    elif role == "client":
        start_snapclient(host, player_arg + extra_args)
    else:
        log("ERROR", f"Invalid ROLE '{role}'")
        sys.exit(1)

if __name__ == "__main__":
    main()
