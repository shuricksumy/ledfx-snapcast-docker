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

def ensure_loopback(index=10):
    """Ensure ALSA loopback device is loaded"""
    try:
        output = subprocess.check_output(["aplay", "-l"], text=True)
        if "Loopback" in output:
            log("INFO", "Loopback device already present")
            return True
        log("INFO", f"Loading snd-aloop module with index={index}")
        subprocess.run(["modprobe", "snd-aloop", f"index={index}"], check=True)
        sleep(2)
        output = subprocess.check_output(["aplay", "-l"], text=True)
        if "Loopback" in output:
            log("INFO", "Loopback device loaded successfully")
            return True
        else:
            log("ERROR", "Loopback device still missing after modprobe")
            return False
    except Exception as e:
        log("ERROR", f"Loopback check failed: {e}")
        return False

def snapclient_supports_player():
    try:
        out = subprocess.run(["/usr/bin/snapclient", "--help"], capture_output=True, text=True, check=True).stdout
        has_player = "--player" in out
        has_sound = "--sound" in out
        log("INFO", f"Snapclient flags: supports --player={has_player}, legacy --sound={has_sound}")
        return has_player
    except Exception as e:
        log("WARNING", f"Could not inspect snapclient --help: {e}. Assuming legacy flags.")
        return False

def build_player_arg(backend, player_opts):
    """Return ['--player', 'backend[:k=v,...]']"""
    arg = backend if not player_opts else f"{backend}:{player_opts}"
    return ["--player", arg]

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
    sound_backend_env = os.getenv("SOUND_BACKEND", "").lower()  # kept for compatibility
    loopback_index = int(os.getenv("LOOPBACK_INDEX", "10"))
    client_id = os.getenv("CLIENT_ID")
    extra_args_env = os.getenv("EXTRA_ARGS", "")
    player_backend_env = os.getenv("PLAYER_BACKEND", "").lower()  # NEW: preferred way
    player_options_env = os.getenv("PLAYER_OPTIONS", "")          # NEW: e.g. "buffer_time=100,device=plughw:10,0"

    extra_args = extra_args_env.split() if extra_args_env else []

    print_aplay_devices()

    # Detect CLI flavor
    use_player_flag = snapclient_supports_player()

    # Determine backend
    backend_choice = player_backend_env or (sound_backend_env if sound_backend_env in ("alsa", "pulse", "loopback") else "")
    if not backend_choice or backend_choice == "loopback":
        backend_choice = auto_detect_backend()

    # Prepare options for --player path
    player_opts = player_options_env.strip()

    if os.getenv("SOUND_BACKEND", "").lower() == "loopback":
        log("INFO", f"SOUND_BACKEND set to 'loopback', checking device at index {loopback_index}")
        if not ensure_loopback(loopback_index):
            log("FATAL", "Loopback backend selected, but loopback device is unavailable. Exiting.")
            sys.exit(1)
        if use_player_flag:
            # If user didn't pass a device, try to provide a sensible default
            if "device=" not in player_opts:
                # NOTE: 'device=' is the common key for snapclient ALSA player. Adjust if your build uses a different key.
                player_opts = (player_opts + "," if player_opts else "") + f"device=plughw:{loopback_index},0"
        else:
            # Legacy flags
            extra_args.append("--sound=alsa")
            extra_args.append(f"--soundcard=plughw:{loopback_index},0")

    elif role in ("client", "ledfx_client"):
        backend = backend_choice
        log("INFO", f"Using audio backend: {backend}")

        # For legacy CLI, we can still hint a soundcard. For new CLI, prefer PLAYER_OPTIONS.
        if not use_player_flag:
            # Legacy construction
            if not any(arg.startswith("--sound=") for arg in extra_args):
                extra_args.append(f"--sound={backend}")
            if backend == "alsa" and device_hint and not any(arg.startswith("--soundcard=") for arg in extra_args):
                resolved = resolve_alsa_device(device_hint)
                if resolved:
                    extra_args.append(f"--soundcard={resolved}")
        else:
            # New construction with --player
            if backend == "pulse" and "device=" not in player_opts and "sink=" not in player_opts:
                # Let Pulse choose default sink unless the user overrides via PLAYER_OPTIONS
                pass
            if backend == "alsa" and device_hint and "device=" not in player_opts:
                # Try to resolve, but only append as a suggestion if we find a concrete plughw string
                resolved = resolve_alsa_device(device_hint)
                if resolved and resolved.startswith(("plughw:", "hw:")):
                    player_opts = (player_opts + "," if player_opts else "") + f"device={resolved}"

    # Host ID / client name
    if not any(arg.startswith("--hostID=") for arg in extra_args):
        if client_id:
            extra_args.append(f"--hostID={client_id}")
            log("INFO", f"Using CLIENT_ID override: {client_id}")
        else:
            extra_args.append("--hostID=AutoClient")

    # Inject --player if we're on the new CLI and it's not supplied in EXTRA_ARGS already
    if use_player_flag and not any(arg == "--player" or arg.startswith("--player") for arg in extra_args):
        extra_args += build_player_arg(backend_choice, player_opts)

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
