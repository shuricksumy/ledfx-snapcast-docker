"""Parameters: seeding, persistence, and refusing anything that reaches argv."""
import json

import pytest

import services
from services import ConfigError


@pytest.fixture
def env(monkeypatch):
    """A known environment, so seeding is tested against fixed values."""
    monkeypatch.setenv("ROLE", "ledfx-suite")
    monkeypatch.setenv("SNAP_HOST", "192.168.1.50")
    monkeypatch.setenv("CLIENT_ID", "Snap-LedFx")
    monkeypatch.setenv("SQUEEZELITE_NAME", "Squeez-LedFx")
    monkeypatch.setenv("SQUEEZELITE_SERVER_PORT", "192.168.1.50:3483")
    monkeypatch.setenv("SQUEEZELITE_MAC", "72:23:98:63:08:13")
    monkeypatch.setenv("SQUEEZELITE_EXTRA_ARGS", "-W")
    monkeypatch.setenv("PULSE_LATENCY_MSEC", "10")
    monkeypatch.delenv("SNAP_CLIENT_ID", raising=False)
    monkeypatch.delenv("EXTRA_ARGS", raising=False)
    return monkeypatch


def test_environment_seeds_the_config(env, tmp_path):
    path = tmp_path / "services.json"
    doc = services.load(str(path))

    assert doc["services"]["squeezelite"]["name"] == "Squeez-LedFx"
    # SNAP_CLIENT_ID falls back to CLIENT_ID, as startup.py always resolved it
    assert doc["services"]["snapclient"]["client_id"] == "Snap-LedFx"
    assert path.exists(), "the seed must be written, not just computed"


def test_the_file_wins_over_the_environment_afterwards(env, tmp_path):
    path = tmp_path / "services.json"
    doc = services.load(str(path))
    doc["services"]["squeezelite"]["name"] = "Renamed-In-Panel"
    services.save(doc, str(path))

    # A stale compose file must not quietly undo a change made in the panel
    env.setenv("SQUEEZELITE_NAME", "From-Compose")
    reloaded = services.load(str(path))
    assert reloaded["services"]["squeezelite"]["name"] == "Renamed-In-Panel"


def test_config_survives_a_restart(env, tmp_path):
    path = tmp_path / "services.json"
    doc = services.load(str(path))
    patched, _ = services.apply_patch(doc, {"services": {"ledfx": {"port": 9000}},
                                            "env": {"PULSE_LATENCY_MSEC": "25"}})
    services.save(patched, str(path))

    reloaded = services.load(str(path))
    assert reloaded["services"]["ledfx"]["port"] == 9000
    assert reloaded["env"]["PULSE_LATENCY_MSEC"] == "25"
    assert "--port" in services.build(reloaded)["ledfx"]["argv"]
    assert "9000" in services.build(reloaded)["ledfx"]["argv"]


def test_saving_is_atomic(env, tmp_path):
    path = tmp_path / "services.json"
    services.save(services.env_defaults(), str(path))
    assert json.loads(path.read_text())["version"] == services.SCHEMA_VERSION
    assert not (tmp_path / "services.json.tmp").exists()


def test_a_corrupt_config_does_not_stop_the_container_booting(env, tmp_path):
    path = tmp_path / "services.json"
    path.write_text("{ this is not json")
    doc = services.load(str(path))
    assert doc["services"]["squeezelite"]["name"] == "Squeez-LedFx"


def test_new_keys_appear_without_deleting_an_old_config(env, tmp_path):
    path = tmp_path / "services.json"
    path.write_text(json.dumps({"version": 1, "role": "ledfx-suite",
                                "services": {"squeezelite": {"name": "Old"}}, "env": {}}))
    doc = services.load(str(path))
    assert doc["services"]["squeezelite"]["name"] == "Old"
    assert "output" in doc["services"]["squeezelite"]     # added by a later image
    assert "PULSE_LATENCY_MSEC" in doc["env"]


def test_reset_goes_back_to_the_environment(env, tmp_path):
    path = tmp_path / "services.json"
    doc = services.load(str(path))
    doc["services"]["squeezelite"]["name"] = "Renamed"
    services.save(doc, str(path))

    services.reset_to_env(str(path))
    assert services.load(str(path))["services"]["squeezelite"]["name"] == "Squeez-LedFx"


# ---- argv -------------------------------------------------------------------


def test_argv_matches_what_the_supervisor_launched_before(env):
    specs = services.build(services.env_defaults("ledfx-suite"))
    assert specs["snapclient"]["argv"] == [
        "snapclient", "--player", "pulse", "--soundcard", "default",
        "--hostID", "Snap-LedFx", "tcp://192.168.1.50",
    ]
    assert specs["squeezelite"]["argv"] == [
        "squeezelite", "-o", "default", "-n", "Squeez-LedFx",
        "-s", "192.168.1.50:3483", "-m", "72:23:98:63:08:13", "-W",
    ]
    assert specs["ledfx"]["argv"] == [
        "/ledfx/venv/bin/ledfx", "--host", "0.0.0.0", "--port", "8888",
    ]
    assert specs["pulseaudio"]["argv"][0] == "pulseaudio"


def test_a_host_with_a_scheme_is_left_alone(env):
    doc = services.env_defaults("ledfx-suite")
    doc["services"]["snapclient"]["host"] = "ws://192.168.1.50:1780"
    assert services.build(doc)["snapclient"]["argv"][-1] == "ws://192.168.1.50:1780"


def test_extra_args_are_split_like_a_shell_but_never_run_through_one(env):
    doc = services.env_defaults("ledfx-suite")
    doc["services"]["squeezelite"]["extra_args"] = "-a '80:4::' -r 44100"
    argv = services.build(doc)["squeezelite"]["argv"]
    assert argv[-4:] == ["-a", "80:4::", "-r", "44100"]


def test_there_is_one_service_set(env):
    assert list(services.build(services.env_defaults())) == [
        "pulseaudio", "snapclient", "squeezelite", "ledfx"]


def test_retired_roles_point_at_where_the_job_went(env):
    # ROLE=snapserver used to work here; it should not fail silently or
    # cryptically now that it does not.
    assert "pipewire-snapclient" in services.RETIRED_ROLES["snapserver"]
    assert "pipewire-snapclient" in services.RETIRED_ROLES["snapclient"]


def test_with_no_environment_at_all_the_image_still_has_a_config(monkeypatch):
    for var in ["ROLE", "SNAP_HOST", "SNAP_CLIENT_ID", "CLIENT_ID", "EXTRA_ARGS",
                "SQUEEZELITE_NAME", "SQUEEZELITE_SERVER_PORT", "SQUEEZELITE_MAC",
                "SQUEEZELITE_EXTRA_ARGS", "SQUEEZELITE_OUTPUT", "PULSE_LATENCY_MSEC",
                "STARTUP_DELAY_SEC", "LEDFX_HOST", "LEDFX_PORT"]:
        monkeypatch.delenv(var, raising=False)
    specs = services.build(services.env_defaults())

    # PulseAudio, LedFx and Squeezelite (which discovers a server) can all run
    # unconfigured; snapclient has nothing to connect to and says so.
    assert specs["pulseaudio"]["enabled"] and specs["ledfx"]["enabled"]
    assert specs["squeezelite"]["enabled"]
    assert not specs["snapclient"]["enabled"]
    assert specs["snapclient"]["blocked"] == "set the Snapserver host first"


def test_giving_a_host_unblocks_snapclient(env):
    doc = services.env_defaults()
    assert services.build(doc)["snapclient"]["blocked"] is None
    assert services.build(doc)["snapclient"]["argv"][-1] == "tcp://192.168.1.50"


def test_pulse_latency_reaches_the_children(env):
    specs = services.build(services.env_defaults("ledfx-suite"))
    assert specs["squeezelite"]["env"]["PULSE_LATENCY_MSEC"] == "10"


# ---- validation -------------------------------------------------------------


@pytest.mark.parametrize("patch,message", [
    ({"services": {"squeezelite": {"name": "bad\nname"}}}, "control characters"),
    ({"services": {"squeezelite": {"name": ""}}}, "cannot be empty"),
    ({"services": {"squeezelite": {"mac": "not-a-mac"}}}, "72:23:98:63:08:13"),
    ({"services": {"squeezelite": {"extra_args": "-a 'unbalanced"}}}, "not valid"),
    ({"services": {"ledfx": {"port": 0}}}, "between 1 and 65535"),
    ({"services": {"ledfx": {"port": "eight"}}}, "must be a number"),
    ({"services": {"snapclient": {"host": "with\x00null"}}}, "control characters"),
    ({"services": {"snapclient": {"client_id": ""}}}, "cannot be empty"),
    ({"services": {"nosuch": {"x": 1}}}, "unknown service"),
    ({"services": {"ledfx": {"nosuch": 1}}}, "unknown parameter"),
    ({"env": {"PULSE_LATENCY_MSEC": "0"}}, "between 1 and 10000"),
    ({"env": {"PULSE_LATENCY_MSEC": "abc"}}, "must be a number"),
    ({"env": {"STARTUP_DELAY_SEC": "-1"}}, "between 0 and 300"),
    ({"env": {"NOT_A_SETTING": "1"}}, "unknown setting"),
])
def test_bad_parameters_are_rejected_with_a_reason(env, patch, message):
    doc = services.env_defaults("ledfx-suite")
    with pytest.raises(ConfigError) as excinfo:
        services.apply_patch(doc, patch)
    assert message in str(excinfo.value)


def test_a_rejected_patch_changes_nothing(env):
    doc = services.env_defaults("ledfx-suite")
    before = json.dumps(doc, sort_keys=True)
    with pytest.raises(ConfigError):
        services.apply_patch(doc, {"services": {"ledfx": {"port": 9000, "host": "bad\nhost"}}})
    assert json.dumps(doc, sort_keys=True) == before


def test_changing_the_buffer_restarts_only_the_services_that_read_it(env):
    doc = services.env_defaults("ledfx-suite")
    _, changed = services.apply_patch(doc, {"env": {"PULSE_LATENCY_MSEC": "50"}})
    # snapclient requests its own buffer and ignores the variable entirely
    assert changed == ["ledfx", "squeezelite"]


def test_editing_one_service_does_not_disturb_the_others(env):
    doc = services.env_defaults("ledfx-suite")
    _, changed = services.apply_patch(doc, {"services": {"squeezelite": {"name": "New"}}})
    assert changed == ["squeezelite"]


def test_an_unchanged_value_is_not_reported_as_a_change(env):
    doc = services.env_defaults("ledfx-suite")
    _, changed = services.apply_patch(doc, {"services": {"squeezelite": {"name": "Squeez-LedFx"}}})
    assert changed == []
