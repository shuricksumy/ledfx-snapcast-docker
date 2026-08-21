#!/usr/bin/env python3
"""Service definitions, their persisted parameters, and how those become argv.

The environment variables documented in the README seed /config/services.json on
first boot; after that the file is authoritative, so a value edited in the panel
survives a container restart and is not silently overwritten by a stale compose
file. `reset_to_env()` goes back the other way when that is what you want.

This module is the only place that knows what a snapclient command line looks
like. The supervisor just runs argv lists.
"""
import json
import os
import re
import shlex
from collections import OrderedDict
from pathlib import Path

CONFIG_PATH = os.environ.get("PANEL_CONFIG", "/config/services.json")
SCHEMA_VERSION = 1

# Anything that reaches an argv list is checked against this. A newline or NUL
# in a name does not fail at exec time - it produces a process running with an
# argument nobody meant to pass - so it is rejected up front with a real error.
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
MAC_RE = re.compile(r"[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}")

# The services, in start order. PulseAudio is first because the clients need it
# up before they connect, and `autospawn = no` in client.conf means they cannot
# start one of their own if it is missing.
SERVICES = ["pulseaudio", "snapclient", "squeezelite", "ledfx"]
ROLE = "ledfx-suite"

# Roles this image used to offer, and where that job now lives. Both duplicated
# a sibling project that does it better - the ALSA player in particular had no
# PipeWire, so no bit-perfect rate following - and keeping them here meant
# shipping a 6MB snapserver plus the whole named-pipe path for nobody.
RETIRED_ROLES = {
    "snapserver": "https://github.com/shuricksumy/pipewire-snapclient",
    "snapclient": "https://github.com/shuricksumy/pipewire-snapclient",
}

# Clients of the PulseAudio daemon. Restarting it has to take these with it and
# bring them back, since they cannot respawn a server themselves.
PULSE_DEPENDENTS = ["snapclient", "squeezelite", "ledfx"]

# Services whose audio path goes through PulseAudio's own buffering, so a
# change to PULSE_LATENCY_MSEC has to re-exec them to take effect. snapclient
# is absent on purpose: it requests its own 100ms buffer and ignores the
# variable entirely.
PULSE_LATENCY_CONSUMERS = ["squeezelite", "ledfx"]


class ConfigError(ValueError):
    """A parameter the panel should reject with 400 rather than launch."""


def _env_flag(name, default=True):
    return os.getenv(name, str(default)).lower() in ("true", "1", "yes", "on")


def _env_int(name, fallback):
    try:
        return int(os.getenv(name, "").strip() or fallback)
    except ValueError:
        return fallback


def env_defaults(role=None):
    """The config document as the environment describes it.

    Every field has a usable default, so the image runs with no environment at
    all: the panel then shows those defaults and anything that needs a server
    address stays stopped until you give it one.
    """
    shared_extra = os.getenv("EXTRA_ARGS", "").strip()
    snap_host = os.getenv("SNAP_HOST", "").strip()

    services = {
        "pulseaudio": {"enabled": True, "extra_args": ""},
        "snapclient": {
            # Without a Snapserver address there is nothing to connect to, so it
            # starts disabled rather than crash-looping against 127.0.0.1. Fill
            # the host in from the panel and press Start.
            "enabled": _env_flag("SNAPCLIENT_LEDFX_ENABLED") and bool(snap_host),
            "host": snap_host,
            # SNAP_CLIENT_ID with CLIENT_ID as a fallback, as startup.py has
            # always resolved it - the older compose example used the latter.
            "client_id": os.getenv("SNAP_CLIENT_ID", os.getenv("CLIENT_ID", "LedFx-Node")),
            "extra_args": "",
        },
        "squeezelite": {
            "enabled": _env_flag("SQUEEZELITE_LEDFX_ENABLED"),
            "name": os.getenv("SQUEEZELITE_NAME", "LedFx"),
            "server": os.getenv("SQUEEZELITE_SERVER_PORT", "").strip(),
            "mac": os.getenv("SQUEEZELITE_MAC", "").strip(),
            # squeezelite is built with the native PulseAudio backend, so -o
            # takes a sink name; "default" means the server's default sink.
            "output": os.getenv("SQUEEZELITE_OUTPUT", "default"),
            "extra_args": os.getenv("SQUEEZELITE_EXTRA_ARGS", "").strip(),
        },
        "ledfx": {
            "enabled": True,
            "host": os.getenv("LEDFX_HOST", "0.0.0.0"),
            "port": _env_int("LEDFX_PORT", 8888),
            "extra_args": "",
        },
    }

    # EXTRA_ARGS reached LedFx in this role, so that is where it still lands.
    if shared_extra:
        services["ledfx"]["extra_args"] = shared_extra

    return {
        "version": SCHEMA_VERSION,
        "role": ROLE,
        "services": services,
        "env": {
            # Read by libpulse inside the children, never by us. It is a
            # Dockerfile ENV, so it is normally already in os.environ.
            "PULSE_LATENCY_MSEC": os.getenv("PULSE_LATENCY_MSEC", "10"),
            "STARTUP_DELAY_SEC": str(_env_int("STARTUP_DELAY_SEC", 2)),
        },
    }


# ---- validation -------------------------------------------------------------


def _text(value, field, allow_empty=False, max_len=256):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ConfigError("%s must be text" % field)
    value = value.strip()
    if not value and not allow_empty:
        raise ConfigError("%s cannot be empty" % field)
    if CONTROL_CHARS.search(value):
        raise ConfigError("%s cannot contain control characters" % field)
    if len(value) > max_len:
        raise ConfigError("%s is too long (max %d characters)" % (field, max_len))
    return value


def _args(value, field):
    """Split a free-text flags field the way a shell would, minus the shell."""
    value = _text(value, field, allow_empty=True, max_len=1024)
    try:
        parts = shlex.split(value)
    except ValueError as exc:
        raise ConfigError("%s is not valid: %s" % (field, exc))
    for part in parts:
        if CONTROL_CHARS.search(part):
            raise ConfigError("%s cannot contain control characters" % field)
    return value


def _port(value, field):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ConfigError("%s must be a number" % field)
    if not 1 <= port <= 65535:
        raise ConfigError("%s must be between 1 and 65535" % field)
    return port


def _bool(value, field):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "1", "yes", "on", "false", "0", "no", "off"):
        return value.lower() in ("true", "1", "yes", "on")
    raise ConfigError("%s must be true or false" % field)


_VALIDATORS = {
    "pulseaudio": {"enabled": _bool, "extra_args": _args},
    "snapclient": {
        "enabled": _bool,
        # Blank is allowed: an unconfigured install should be editable in the
        # panel, not rejected. Starting without one is what gets refused.
        "host": lambda v, f: _text(v, f, allow_empty=True, max_len=253),
        "client_id": lambda v, f: _text(v, f, max_len=128),
        "extra_args": _args,
    },
    "squeezelite": {
        "enabled": _bool,
        "name": lambda v, f: _text(v, f, max_len=128),
        "server": lambda v, f: _text(v, f, allow_empty=True, max_len=253),
        "mac": lambda v, f: _mac(v, f),
        "output": lambda v, f: _text(v, f, max_len=128),
        "extra_args": _args,
    },
    "ledfx": {
        "enabled": _bool,
        "host": lambda v, f: _text(v, f, max_len=253),
        "port": _port,
        "extra_args": _args,
    },
}


def _mac(value, field):
    value = _text(value, field, allow_empty=True, max_len=17)
    if value and not MAC_RE.fullmatch(value):
        raise ConfigError("%s must look like 72:23:98:63:08:13" % field)
    return value


def _env_value(key, value):
    if key == "PULSE_LATENCY_MSEC":
        try:
            msec = int(value)
        except (TypeError, ValueError):
            raise ConfigError("PULSE_LATENCY_MSEC must be a number")
        if not 1 <= msec <= 10000:
            raise ConfigError("PULSE_LATENCY_MSEC must be between 1 and 10000")
        return str(msec)
    if key == "STARTUP_DELAY_SEC":
        try:
            secs = int(value)
        except (TypeError, ValueError):
            raise ConfigError("STARTUP_DELAY_SEC must be a number")
        if not 0 <= secs <= 300:
            raise ConfigError("STARTUP_DELAY_SEC must be between 0 and 300")
        return str(secs)
    raise ConfigError("unknown setting %s" % key)


def apply_patch(doc, patch):
    """Merge a validated patch into a copy of `doc`; raise ConfigError on junk.

    Returns (new_doc, changed_service_names). Nothing is written and no process
    is touched unless every field in the patch passes.
    """
    if not isinstance(patch, dict):
        raise ConfigError("expected an object")

    new = json.loads(json.dumps(doc))  # deep copy; the doc is plain JSON
    changed = set()

    for name, fields in (patch.get("services") or {}).items():
        if name not in new["services"]:
            raise ConfigError("unknown service %s" % name)
        if not isinstance(fields, dict):
            raise ConfigError("%s must be an object" % name)
        validators = _VALIDATORS[name]
        for field, value in fields.items():
            if field not in validators:
                raise ConfigError("unknown parameter %s.%s" % (name, field))
            clean = validators[field](value, "%s.%s" % (name, field))
            if new["services"][name].get(field) != clean:
                new["services"][name][field] = clean
                changed.add(name)

    for key, value in (patch.get("env") or {}).items():
        clean = _env_value(key, value)
        if new["env"].get(key) != clean:
            new["env"][key] = clean
            if key == "PULSE_LATENCY_MSEC":
                changed.update(PULSE_LATENCY_CONSUMERS)
            else:
                # STARTUP_DELAY_SEC is read at launch, not by a running
                # process; it applies to the next start on its own.
                changed.update(())

    return new, sorted(changed)


# ---- persistence ------------------------------------------------------------


def load(path=None, role=None):
    """The stored document, seeded from the environment the first time."""
    path = path or CONFIG_PATH
    defaults = env_defaults(role)
    try:
        stored = json.loads(Path(path).read_text())
    except FileNotFoundError:
        save(defaults, path)
        return defaults
    except (OSError, ValueError) as exc:
        # A corrupt or unreadable config must not stop the container booting -
        # the whole point of this image is that audio comes up unattended.
        print("[panel] ignoring unreadable %s (%s); using environment defaults" % (path, exc), flush=True)
        return defaults

    # Merge so a key added by a later image version appears without the user
    # having to delete their config.
    merged = defaults
    for name, fields in (stored.get("services") or {}).items():
        if name in merged["services"] and isinstance(fields, dict):
            merged["services"][name].update(fields)
    for key, value in (stored.get("env") or {}).items():
        if key in merged["env"]:
            merged["env"][key] = str(value)
    if stored.get("role"):
        merged["role"] = str(stored["role"]).lower()
    return merged


def save(doc, path=None):
    """Write atomically: a half-written config would break the next boot."""
    path = path or CONFIG_PATH
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        tmp = str(path) + ".tmp"
        with open(tmp, "w") as handle:
            json.dump(doc, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        # Read-only or unmounted /config: keep running with what we have in
        # memory rather than refusing to start.
        print("[panel] could not write %s (%s); changes last until restart" % (path, exc), flush=True)
    return doc


def reset_to_env(path=None, role=None):
    return save(env_defaults(role), path)


# ---- argv -------------------------------------------------------------------


def build(doc, **_ignored):
    """Turn the stored document into {name: {argv, env, enabled}} in start order.

    A service whose required parameter is missing comes back disabled with a
    `blocked` reason, so the panel can say why rather than launching something
    that cannot work.
    """
    svc = doc["services"]
    env = doc.get("env", {})
    # libpulse reads this from the child's environment; snapclient sets its own
    # buffer and is unaffected either way.
    child_env = {"PULSE_LATENCY_MSEC": str(env.get("PULSE_LATENCY_MSEC", "10"))}

    specs = OrderedDict()
    for name in SERVICES:
        conf = svc[name]
        blocked = None

        if name == "pulseaudio":
            argv = ["pulseaudio", "--exit-idle-time=-1", "--disallow-exit", "--log-target=stderr"]
        elif name == "snapclient":
            host = conf.get("host", "").strip()
            argv = ["snapclient", "--player", "pulse", "--soundcard", "default",
                    "--hostID", conf["client_id"]]
            argv += shlex.split(conf.get("extra_args", ""))
            if host:
                argv.append(host if "://" in host else "tcp://%s" % host)
            else:
                blocked = "set the Snapserver host first"
        elif name == "squeezelite":
            # No server is a valid setup: squeezelite discovers one on the LAN.
            argv = ["squeezelite", "-o", conf["output"], "-n", conf["name"]]
            if conf.get("server"):
                argv += ["-s", conf["server"]]
            if conf.get("mac"):
                argv += ["-m", conf["mac"]]
            argv += shlex.split(conf.get("extra_args", ""))
        elif name == "ledfx":
            argv = ["/ledfx/venv/bin/ledfx", "--host", conf["host"], "--port", str(conf["port"])]
            argv += shlex.split(conf.get("extra_args", ""))
        else:  # pragma: no cover - SERVICES is the only source of names
            continue

        specs[name] = {
            "argv": argv,
            "env": dict(child_env),
            "enabled": bool(conf.get("enabled", True)) and blocked is None,
            "blocked": blocked,
        }
    return specs
