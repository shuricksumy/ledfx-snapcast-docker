import os
import sys
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fake_service.py")


def fake_spec(name, mode="run", enabled=True):
    return {"argv": [sys.executable, FAKE, name, mode], "env": {}, "enabled": enabled}


@pytest.fixture
def fast(monkeypatch):
    """Shrink the timings so a backoff test takes milliseconds, not a minute."""
    import supervisor as sup_mod

    monkeypatch.setattr(sup_mod, "INIT_DELAY", 0.2)
    monkeypatch.setattr(sup_mod, "MAX_DELAY", 0.4)
    monkeypatch.setattr(sup_mod, "STABLE_RUN_S", 0.3)
    monkeypatch.setattr(sup_mod, "STOP_GRACE_S", 1)
    return sup_mod


class RunningSupervisor:
    """A supervisor with its loop in a thread, as it runs in the container.

    Intents are only carried out by that loop, so a test that posts one
    without it would be testing nothing.
    """

    def __init__(self, specs, tmp_path, **kwargs):
        from supervisor import Supervisor

        self.sup = Supervisor(specs, health_path=str(tmp_path / "health"), **kwargs)
        self.shutdown = threading.Event()
        self.thread = None

    def start(self):
        self.sup.autostart()
        self.thread = threading.Thread(target=self.sup.run, args=(self.shutdown,), daemon=True)
        self.thread.start()
        return self.sup

    def close(self):
        self.shutdown.set()
        if self.thread:
            self.thread.join(timeout=10)
        self.sup.stop_all()


@pytest.fixture
def make_supervisor(fast, tmp_path):
    created = []

    def _make(specs, **kwargs):
        kwargs.setdefault("startup_delay", 0)
        runner = RunningSupervisor(specs, tmp_path, **kwargs)
        created.append(runner)
        return runner.start()

    yield _make
    for runner in created:
        runner.close()


@pytest.fixture
def sup(make_supervisor):
    """The ledfx-suite service set, over fakes."""
    return make_supervisor(
        {
            "pulseaudio": fake_spec("pulseaudio"),
            "snapclient": fake_spec("snapclient"),
            "squeezelite": fake_spec("squeezelite"),
            "ledfx": fake_spec("ledfx"),
        },
        dependents=["snapclient", "squeezelite", "ledfx"],
    )
