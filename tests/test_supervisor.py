"""What the supervisor must keep doing once a browser can drive it."""
import os
import time

from conftest import fake_spec


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def all_running(sup):
    return all(sup.services[n].running for n in sup.order)


def test_a_crashing_service_is_restarted_with_backoff(fast, make_supervisor):
    sup = make_supervisor({"ledfx": fake_spec("ledfx", "crash")})
    svc = sup.services["ledfx"]

    assert wait_until(lambda: svc.state == "backoff")
    first_delay = svc.delay
    assert wait_until(lambda: svc.restarts >= 1)
    assert svc.delay >= first_delay          # each crash waits longer
    assert wait_until(lambda: svc.restarts >= 2)
    assert svc.delay <= fast.MAX_DELAY       # ...up to the cap


def test_a_stopped_service_stays_stopped(sup):
    svc = sup.services["squeezelite"]
    assert wait_until(lambda: svc.running)

    sup.stop("squeezelite").wait(5)
    assert svc.state == "stopped"

    # The old loop restarted anything that exited. The running loop must not
    # undo a deliberate stop, however long it keeps ticking.
    time.sleep(1.0)
    assert svc.state == "stopped"
    assert svc.proc is None
    assert svc.restarts == 0


def test_stop_leaves_no_orphan(sup):
    svc = sup.services["snapclient"]
    assert wait_until(lambda: svc.running)
    pid = svc.proc.pid

    sup.stop("snapclient").wait(5)
    assert not pid_alive(pid)


def test_stop_kills_a_child_that_ignores_sigterm(fast, make_supervisor):
    sup = make_supervisor({"ledfx": fake_spec("ledfx", "stubborn")})
    svc = sup.services["ledfx"]
    assert wait_until(lambda: svc.running)
    pid = svc.proc.pid

    sup.stop("ledfx").wait(10)
    assert not pid_alive(pid)


def test_restarting_pulseaudio_cycles_its_dependents(sup):
    assert wait_until(lambda: all_running(sup))
    before = {n: sup.services[n].proc.pid for n in sup.order}

    sup.restart("pulseaudio").wait(10)

    # Clients cannot respawn a server of their own (autospawn = no in
    # client.conf), so they have to be taken down and brought back with it.
    for name in sup.order:
        assert sup.services[name].running, name
        assert sup.services[name].proc.pid != before[name], name
        assert not pid_alive(before[name]), name


def test_a_deliberately_stopped_dependent_is_not_revived_by_a_pulse_restart(sup):
    assert wait_until(lambda: all_running(sup))

    sup.stop("squeezelite").wait(5)
    sup.restart("pulseaudio").wait(10)

    assert sup.services["pulseaudio"].running
    assert wait_until(lambda: sup.services["snapclient"].running)
    assert sup.services["squeezelite"].state == "stopped"


def test_health_ignores_a_deliberate_stop(sup):
    assert wait_until(sup.healthy)

    sup.stop("squeezelite").wait(5)
    # "Everything that should be running is running" - a service the operator
    # stopped is not a fault, so the container stays healthy.
    assert sup.healthy()


def test_health_is_false_while_a_service_crash_loops(fast, make_supervisor):
    sup = make_supervisor({"ledfx": fake_spec("ledfx", "crash")})
    assert wait_until(lambda: sup.services["ledfx"].restarts >= 1)
    assert not sup.healthy()


def test_health_file_is_touched_once_everything_settles(sup, tmp_path):
    assert wait_until(lambda: (tmp_path / "health").exists())


def test_disabled_services_are_not_started(fast, make_supervisor):
    sup = make_supervisor({"ledfx": fake_spec("ledfx", enabled=False)})
    time.sleep(0.5)
    assert sup.services["ledfx"].state == "stopped"
    assert sup.services["ledfx"].proc is None


def test_a_stopped_service_can_be_started_again(sup):
    svc = sup.services["ledfx"]
    assert wait_until(lambda: svc.running)
    sup.stop("ledfx").wait(5)
    assert svc.state == "stopped"

    sup.start("ledfx").wait(5)
    assert wait_until(lambda: svc.running)


def test_logs_are_captured_into_a_bounded_ring(sup):
    from supervisor import LOG_LINES

    svc = sup.services["ledfx"]
    assert wait_until(lambda: len(svc.logs) > 0)
    assert any("started pid=" in line for line in svc.logs)
    assert svc.logs.maxlen == LOG_LINES == 200


def test_child_environment_carries_pulse_latency(fast, make_supervisor):
    spec = fake_spec("squeezelite")
    spec["env"] = {"PULSE_LATENCY_MSEC": "42"}
    sup = make_supervisor({"squeezelite": spec})
    svc = sup.services["squeezelite"]
    assert wait_until(lambda: any("PULSE_LATENCY_MSEC=42" in line for line in svc.logs))


def test_reconfigure_restarts_only_what_changed(sup):
    assert wait_until(lambda: all_running(sup))
    before = {n: sup.services[n].proc.pid for n in sup.order}

    sup.reconfigure({"squeezelite": fake_spec("squeezelite-renamed")}, ["squeezelite"]).wait(10)

    assert wait_until(lambda: sup.services["squeezelite"].running)
    assert sup.services["squeezelite"].proc.pid != before["squeezelite"]
    for name in ["pulseaudio", "snapclient", "ledfx"]:
        assert sup.services[name].proc.pid == before[name], name


def test_stop_all_leaves_nothing_behind(sup):
    assert wait_until(lambda: all_running(sup))
    pids = [sup.services[n].proc.pid for n in sup.order]

    sup.stop_all()

    assert not any(pid_alive(pid) for pid in pids)


def test_editing_one_service_does_not_revive_another_that_was_stopped(sup):
    """A stop from the panel and a stored enabled=true legitimately differ, so
    reconfigure must not treat that disagreement as something to correct."""
    assert wait_until(lambda: all_running(sup))
    sup.stop("squeezelite").wait(5)

    # An unrelated edit: squeezelite is in the specs (everything always is) and
    # still carries enabled=True from the stored config.
    specs = {n: fake_spec(n) for n in sup.order}
    sup.reconfigure(specs, ["ledfx"]).wait(10)

    assert wait_until(lambda: sup.services["ledfx"].running)
    assert sup.services["squeezelite"].state == "stopped"
    assert sup.services["squeezelite"].proc is None
