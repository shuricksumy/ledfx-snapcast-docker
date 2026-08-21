"""The HTTP surface, against a real supervisor over fake binaries."""
import base64
import sys
import time

import pytest

import panel
import services
from conftest import FAKE, fake_spec


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def client(sup, tmp_path, monkeypatch):
    monkeypatch.setattr(services, "CONFIG_PATH", str(tmp_path / "services.json"))
    monkeypatch.setattr(panel, "ADMIN_PASSWORD", "")

    # Keep the real validate -> build -> reconfigure path, but point the argv at
    # the fakes: the container has snapclient and ledfx on PATH, a test host
    # does not, and the point here is the plumbing, not the binaries.
    real_build = services.build

    def build_with_fakes(doc, **kwargs):
        specs = real_build(doc, **kwargs)
        for name, spec in specs.items():
            spec["argv"] = [sys.executable, FAKE, name, "run"]
        return specs

    monkeypatch.setattr(services, "build", build_with_fakes)

    doc = services.env_defaults("ledfx-suite")
    app = panel.create_app(sup, doc)
    app.config["TESTING"] = True
    with app.test_client() as c:
        c.sup = sup
        yield c


def test_the_page_is_served(client):
    body = client.get("/").get_data(as_text=True)
    # Ingress strips a path prefix, so the page must resolve its API relative
    # to the document rather than from the root.
    assert "document.baseURI" in body


def test_services_are_listed_with_their_state(client):
    data = client.get("/api/services").get_json()
    names = [s["name"] for s in data["services"]]
    assert names == ["pulseaudio", "snapclient", "squeezelite", "ledfx"]
    assert all("command" in s for s in data["services"])


def test_stop_and_start_through_the_api(client):
    assert client.post("/api/services/squeezelite/stop").status_code == 200
    assert client.get("/api/services").get_json()["services"][2]["state"] == "stopped"

    assert client.post("/api/services/squeezelite/start").status_code == 200
    assert wait_until(lambda: client.sup.services["squeezelite"].running)


def test_restart_through_the_api_replaces_the_process(client):
    assert wait_until(lambda: client.sup.services["ledfx"].running)
    before = client.sup.services["ledfx"].proc.pid
    assert client.post("/api/services/ledfx/restart").status_code == 200
    assert wait_until(lambda: client.sup.services["ledfx"].proc.pid != before)


def test_unknown_services_and_actions_are_refused(client):
    assert client.post("/api/services/nosuch/start").status_code == 404
    assert client.post("/api/services/ledfx/explode").status_code == 400


def test_logs_are_served_for_a_service(client):
    assert wait_until(lambda: len(client.sup.services["ledfx"].logs) > 0)
    data = client.get("/api/services/ledfx/logs").get_json()
    assert any("started pid=" in line for line in data["logs"])
    assert client.get("/api/services/nosuch/logs").status_code == 404


def test_config_is_returned_and_patched(client):
    assert client.get("/api/config").get_json()["role"] == "ledfx-suite"

    res = client.patch("/api/config", json={"services": {"squeezelite": {"name": "Panel-Named"}}})
    assert res.status_code == 200
    assert res.get_json()["changed"] == ["squeezelite"]
    assert client.get("/api/config").get_json()["services"]["squeezelite"]["name"] == "Panel-Named"


def test_a_bad_parameter_is_a_400_with_a_reason_and_no_restart(client):
    assert wait_until(lambda: client.sup.services["squeezelite"].running)
    before = client.sup.services["squeezelite"].proc.pid

    res = client.patch("/api/config", json={"services": {"squeezelite": {"name": "bad\nname"}}})
    assert res.status_code == 400
    assert "control characters" in res.get_json()["error"]
    # A rejected edit must not have disturbed the running service
    time.sleep(0.3)
    assert client.sup.services["squeezelite"].proc.pid == before


def test_patching_a_parameter_restarts_only_that_service(client):
    assert wait_until(lambda: all(client.sup.services[n].running for n in client.sup.order))
    before = {n: client.sup.services[n].proc.pid for n in client.sup.order}

    client.patch("/api/config", json={"services": {"ledfx": {"port": 9001}}})

    assert wait_until(lambda: client.sup.services["ledfx"].proc.pid != before["ledfx"])
    for name in ["pulseaudio", "snapclient", "squeezelite"]:
        assert client.sup.services[name].proc.pid == before[name], name


def test_disabling_a_service_through_config_stops_it(client):
    assert wait_until(lambda: client.sup.services["squeezelite"].running)
    client.patch("/api/config", json={"services": {"squeezelite": {"enabled": False}}})
    assert wait_until(lambda: client.sup.services["squeezelite"].state == "stopped")


def test_reset_restores_the_environment_defaults(client):
    client.patch("/api/config", json={"services": {"squeezelite": {"name": "Panel-Named"}}})
    assert client.post("/api/config/reset").status_code == 200
    name = client.get("/api/config").get_json()["services"]["squeezelite"]["name"]
    assert name != "Panel-Named"


def test_health_endpoint_follows_the_supervisor(client):
    assert wait_until(lambda: client.get("/api/health").status_code == 200)
    client.post("/api/services/squeezelite/stop")
    # A deliberate stop is not a fault
    assert client.get("/api/health").status_code == 200


def test_auth_is_off_without_a_password(client):
    assert client.get("/api/services").status_code == 200


def test_auth_gates_everything_when_a_password_is_set(sup, monkeypatch):
    monkeypatch.setattr(panel, "ADMIN_PASSWORD", "secret")
    monkeypatch.setattr(panel, "ADMIN_USER", "admin")
    app = panel.create_app(sup, services.env_defaults("ledfx-suite"))
    with app.test_client() as c:
        assert c.get("/api/services").status_code == 401
        assert c.get("/").status_code == 401          # the page too, not just the API
        token = base64.b64encode(b"admin:secret").decode()
        assert c.get("/api/services", headers={"Authorization": "Basic " + token}).status_code == 200
        bad = base64.b64encode(b"admin:wrong").decode()
        assert c.get("/api/services", headers={"Authorization": "Basic " + bad}).status_code == 401
