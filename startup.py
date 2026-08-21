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


def handle_signal(signum, _frame):
    log("INFO", "📴 Caught %s, shutting down..." % signal.Signals(signum).name)
    _shutdown.set()


def main():
    try:
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

        cleanup()

        role = os.getenv("ROLE", services.ROLE).lower()
        if role in services.RETIRED_ROLES:
            # Tell them where the job went rather than dying with "unknown".
            log("ERROR", "ROLE=%s is no longer part of this image - it duplicated "
                         "a project that does it better. Use %s"
                % (role, services.RETIRED_ROLES[role]))
            sys.exit(1)

        doc = services.load()
        log("INFO", "🌈 Mode: LedFx Suite (Pulse Bridge)")

        specs = services.build(doc)
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
                    target=panel.serve, args=(sup, doc), daemon=True, name="panel"
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
