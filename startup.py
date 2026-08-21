#!/usr/bin/env python3
"""PID 1: prepare the environment, then supervise the role's services.

The web panel runs in a thread of this same process, deliberately: it has to be
the children's parent to signal them, and a second supervisor in its own
process would fight this one over who restarts what.
"""
import os
import shutil
import signal
import sys
import threading
import time
from pathlib import Path

import services
import supervisor
from supervisor import Supervisor, log

_shutdown = threading.Event()


def show_config(file_path):
    try:
        if os.path.exists(file_path):
            log("INFO", "📄 Content of %s:" % file_path)
            print("-" * 40, flush=True)
            content = Path(file_path).read_text()
            print(content if content.strip() else "[Empty File]", flush=True)
            print("-" * 40, flush=True)
    except Exception:
        pass


def cleanup():
    log("INFO", "🧹 Performing pre-start cleanup...")
    for path_str in ["/tmp/.esd-*", "/tmp/pulse-*", supervisor.HEALTH_PATH]:
        try:
            base_dir = os.path.dirname(path_str)
            if os.path.exists(base_dir):
                for item in Path(base_dir).glob(os.path.basename(path_str)):
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
        except Exception:
            pass


def setup_fifos(fifo_dir):
    for pipe_name in ["snapfifo", "snapfifo_ledfx"]:
        path = "%s/%s" % (fifo_dir, pipe_name)
        try:
            if not os.path.exists(path):
                log("INFO", "📂 Creating Named Pipe at %s" % path)
                os.mkfifo(path)
            os.chmod(path, 0o666)
        except Exception as exc:
            log("ERROR", "❌ Failed to setup FIFO %s: %s" % (path, exc))


def snapserver_config(fifo_dir):
    """The config snapserver should read, retargeted if FIFO_DIR moved."""
    config_file = "/config/snapserver.conf" if os.path.exists("/config/snapserver.conf") else "/etc/snapserver.conf"
    if fifo_dir != "/tmp" and config_file == "/etc/snapserver.conf":
        # The shipped config hardcodes /tmp, so retarget it rather than making
        # FIFO_DIR require a hand-written snapserver.conf
        rendered = "/tmp/snapserver.conf"
        Path(rendered).write_text(
            Path(config_file).read_text().replace("/tmp/snapfifo", "%s/snapfifo" % fifo_dir)
        )
        config_file = rendered
    show_config(config_file)
    return config_file


def handle_signal(signum, _frame):
    log("INFO", "📴 Caught %s, shutting down..." % signal.Signals(signum).name)
    _shutdown.set()


def main():
    try:
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        cleanup()

        doc = services.load()
        role = doc["role"]
        if role not in services.ROLE_SERVICES:
            log("ERROR", "Unknown Role: %s" % role)
            sys.exit(1)

        log("INFO", "🛠️ System initialized for Role: %s" % role.upper())

        fifo_dir = doc["env"].get("FIFO_DIR", "/tmp")
        config_file = None
        if role == "snapserver":
            setup_fifos(fifo_dir)
            config_file = snapserver_config(fifo_dir)
        elif role == "ledfx-suite":
            log("INFO", "🌈 Mode: LedFx Suite (Pulse Bridge)")

        specs = services.build(doc, fifo_dir=fifo_dir, config_file=config_file)
        sup = Supervisor(
            specs,
            startup_delay=int(doc["env"].get("STARTUP_DELAY_SEC", 2)),
            dependents=services.PULSE_DEPENDENTS,
        )

        # The panel is optional scenery: anyone who never opens it should not be
        # able to tell it is there, so a failure to bind must not stop audio.
        if os.getenv("PANEL_ENABLED", "true").lower() in ("true", "1", "yes", "on"):
            try:
                import panel
                threading.Thread(
                    target=panel.serve, args=(sup, doc, config_file), daemon=True, name="panel"
                ).start()
            except Exception as exc:
                log("ERROR", "🌐 Panel failed to start (%s); services continue" % exc)

        sup.autostart()
        sup.run(_shutdown)
        sup.stop_all()

    except SystemExit:
        raise
    except Exception as exc:
        log("ERROR", "🛑 Global script crash: %s" % exc)
        time.sleep(5)
        sys.exit(1)


if __name__ == "__main__":
    main()
