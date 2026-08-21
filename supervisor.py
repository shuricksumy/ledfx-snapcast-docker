#!/usr/bin/env python3
"""Supervises the role's processes: backoff, log pumping, health, shutdown.

One thread owns every child process. The panel never calls Popen, terminate or
kill - it posts an intent and waits for the loop to carry it out. That is what
makes "stop" atomic against a restart that is one tick from firing: there is no
window in which an API thread reads the state, decides, and acts while the loop
does the same thing with the same child.
"""
import os
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

INIT_DELAY = 5
MAX_DELAY = 60
STABLE_RUN_S = 30      # ran longer than this -> reset backoff on next crash
STOP_GRACE_S = 8       # time children get to exit before SIGKILL
TICK_S = 0.25          # loop period; the panel should feel immediate
LOG_LINES = 200
HEALTH_PATH = os.environ.get("HEALTH_PATH", "/tmp/supervisor_health")


def _emit(line):
    """One write per line: print() writes the text and the newline separately,
    and with the panel, the loop and every child's pump thread all writing to
    the same stdout, that interleaves them mid-line."""
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def log(level, msg):
    _emit("[%s] [%s]  ➡️  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), level, msg))


class Service:
    """One supervised process and the state the panel reports."""

    def __init__(self, name, argv, env=None, enabled=True):
        self.name = name
        self.argv = list(argv)
        self.env = dict(env or {})
        self.desired = bool(enabled)     # what the operator wants
        self.proc = None
        self.delay = INIT_DELAY
        self.restart_at = None
        self.started_at = None
        self.restarts = 0
        self.last_exit = None
        self.logs = deque(maxlen=LOG_LINES)

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def state(self):
        if self.running:
            return "running"
        if not self.desired:
            return "stopped"
        if self.restart_at is not None:
            return "backoff"
        return "starting"

    def status(self, now=None):
        now = now or time.monotonic()
        return {
            "name": self.name,
            "state": self.state,
            "desired": self.desired,
            "running": self.running,
            "pid": self.proc.pid if self.running else None,
            "uptime": (now - self.started_at) if (self.running and self.started_at) else 0,
            "restarts": self.restarts,
            "last_exit": self.last_exit,
            "retry_in": max(0, self.restart_at - now) if self.restart_at else 0,
            "command": " ".join(self.argv),
        }

    def record(self, line):
        self.logs.append("%s %s" % (time.strftime("%H:%M:%S"), line.rstrip()))


class Supervisor:
    def __init__(self, specs, startup_delay=2, health_path=HEALTH_PATH, dependents=None):
        self.services = {}
        self.order = []
        for name, spec in specs.items():
            self.services[name] = Service(name, spec["argv"], spec.get("env"), spec.get("enabled", True))
            self.order.append(name)
        self.startup_delay = startup_delay
        self.health_path = health_path
        self.dependents = list(dependents or [])
        self._intents = queue.Queue()
        self._wake = threading.Event()
        self._shutdown = threading.Event()

    # ---- intents: called from Flask threads, executed by the loop ----------

    def _post(self, fn):
        done = threading.Event()
        self._intents.put((fn, done))
        self._wake.set()
        return done

    def start(self, name):
        return self._post(lambda: self._do_start(name))

    def stop(self, name):
        return self._post(lambda: self._do_stop(name))

    def restart(self, name):
        return self._post(lambda: self._do_restart(name))

    def reconfigure(self, specs, changed):
        """Adopt new argv/env and restart only the services that changed."""
        return self._post(lambda: self._do_reconfigure(specs, changed))

    # ---- process control: loop thread only --------------------------------

    def _spawn(self, svc):
        log("INFO", "🚀 Starting %s: %s" % (svc.name, " ".join(svc.argv)))
        env = os.environ.copy()
        env.update(svc.env)
        try:
            svc.proc = subprocess.Popen(
                svc.argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env,
            )
        except OSError as exc:
            svc.proc = None
            svc.last_exit = str(exc)
            svc.record("cannot start: %s" % exc)
            log("ERROR", "❌ Cannot start %s: %s" % (svc.name, exc))
            svc.restart_at = time.monotonic() + svc.delay
            svc.delay = min(svc.delay * 2, MAX_DELAY)
            return
        svc.started_at = time.monotonic()
        svc.restart_at = None
        threading.Thread(target=self._pump, args=(svc, svc.proc), daemon=True).start()

    def _pump(self, svc, proc):
        """Children's output goes to stdout as before, and to the ring buffer."""
        try:
            for line in iter(proc.stdout.readline, ""):
                if line:
                    _emit("[%s] %s" % (svc.name, line.rstrip()))
                    svc.record(line)
        except Exception:
            pass

    def _terminate(self, svc):
        proc = svc.proc
        if proc is None or proc.poll() is not None:
            svc.proc = None
            return
        log("INFO", "⏹️ Stopping %s..." % svc.name)
        proc.terminate()
        try:
            proc.wait(timeout=STOP_GRACE_S)
        except subprocess.TimeoutExpired:
            log("WARN", "⚠️ '%s' ignored SIGTERM, killing it" % svc.name)
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        svc.proc = None

    def _do_start(self, name):
        svc = self.services[name]
        svc.desired = True
        svc.delay = INIT_DELAY
        svc.restart_at = None
        if not svc.running:
            self._spawn(svc)

    def _do_stop(self, name):
        svc = self.services[name]
        # Clearing desired first is what stops the loop from restarting it: by
        # the time _terminate returns, no scheduled restart can still fire.
        svc.desired = False
        svc.restart_at = None
        self._terminate(svc)
        svc.record("stopped by operator")

    def _do_restart(self, name):
        if name == "pulseaudio":
            return self._do_restart_pulse()
        self._do_stop(name)
        self._do_start(name)

    def _do_restart_pulse(self):
        """PulseAudio's clients cannot respawn a server (autospawn = no in
        client.conf), so a bare restart would leave them crash-looping against
        a socket that briefly does not exist. Take them down with it."""
        resume = [n for n in self.dependents
                  if n in self.services and self.services[n].desired]
        for name in reversed(resume):
            self._terminate(self.services[name])
        self._do_stop("pulseaudio")
        self._do_start("pulseaudio")
        if self.startup_delay > 0:
            log("INFO", "⏱️ Waiting %ss for PulseAudio readiness..." % self.startup_delay)
            time.sleep(self.startup_delay)
        for name in resume:
            svc = self.services[name]
            svc.delay = INIT_DELAY
            svc.restart_at = None
            self._spawn(svc)

    def _do_reconfigure(self, specs, changed):
        pulse_changed = "pulseaudio" in changed
        for name, spec in specs.items():
            svc = self.services.get(name)
            if svc is None:
                continue
            svc.argv = list(spec["argv"])
            svc.env = dict(spec.get("env") or {})
            # Only act on enabled for a service the caller says changed. Acting
            # on every disagreement would let an edit to one service revive
            # another that the operator had stopped from the panel, since a
            # runtime stop and a stored enabled=true legitimately differ.
            if name not in changed:
                continue
            wanted = bool(spec.get("enabled", True))
            if wanted != svc.desired:
                (self._do_start if wanted else self._do_stop)(name)
                changed = [c for c in changed if c != name]
        if pulse_changed:
            self._do_restart_pulse()
            return
        for name in changed:
            svc = self.services.get(name)
            if svc is not None and svc.desired:
                self._do_restart(name)

    # ---- loop --------------------------------------------------------------

    def autostart(self):
        for name in self.order:
            svc = self.services[name]
            if not svc.desired:
                log("INFO", "⏭️ %s is disabled; not starting it" % name)
                continue
            self._spawn(svc)
            if name == "pulseaudio" and self.startup_delay > 0:
                log("INFO", "⏱️ Waiting %ss for PulseAudio readiness..." % self.startup_delay)
                time.sleep(self.startup_delay)

    def tick(self, now=None):
        now = now or time.monotonic()
        self._drain_intents()

        for name in self.order:
            svc = self.services[name]
            if not svc.desired:
                continue
            if svc.running:
                if svc.started_at and (now - svc.started_at) > STABLE_RUN_S:
                    svc.delay = INIT_DELAY
                continue

            rc = svc.proc.poll() if svc.proc is not None else None
            if svc.proc is not None:
                run_time = now - (svc.started_at or now)
                svc.last_exit = rc
                svc.proc = None
                if run_time > STABLE_RUN_S:
                    svc.delay = INIT_DELAY
                log("WARN", "⚠️ '%s' exited (code %s, ran %.0fs). Restarting in %ss..."
                    % (name, rc, run_time, svc.delay))
                svc.record("exited with %s; restarting in %ss" % (rc, svc.delay))
                svc.restart_at = now + svc.delay
                svc.delay = min(svc.delay * 2, MAX_DELAY)
            elif svc.restart_at is not None and now >= svc.restart_at:
                svc.restarts += 1
                self._spawn(svc)
            elif svc.restart_at is None:
                self._spawn(svc)

        self._update_health(now)

    def _drain_intents(self):
        while True:
            try:
                fn, done = self._intents.get_nowait()
            except queue.Empty:
                return
            try:
                fn()
            except Exception as exc:  # an API mistake must not kill the loop
                log("ERROR", "🛑 intent failed: %s" % exc)
            finally:
                done.set()

    def healthy(self, now=None):
        """Everything that should be running is running, and has settled.

        Deliberately stopped services are excluded - otherwise using the panel
        to stop one would make the container unhealthy. Stability is still
        required of the rest, so a crash loop is not reported as healthy.
        """
        now = now or time.monotonic()
        for svc in self.services.values():
            if not svc.desired:
                continue
            if not svc.running or svc.restart_at is not None:
                return False
            if not svc.started_at or (now - svc.started_at) <= STABLE_RUN_S:
                return False
        return True

    def _update_health(self, now):
        if self.healthy(now):
            try:
                Path(self.health_path).touch()
            except OSError:
                pass

    def run(self, shutdown):
        log("INFO", "✅ All services running. Monitoring for crashes...")
        while not shutdown.is_set():
            self.tick()
            self._wake.wait(TICK_S)
            self._wake.clear()

    def stop_all(self):
        for name in reversed(self.order):
            svc = self.services[name]
            svc.desired = False
            svc.restart_at = None
            self._terminate(svc)
        log("INFO", "👋 All services stopped.")

    def status(self):
        now = time.monotonic()
        return [self.services[n].status(now) for n in self.order]
