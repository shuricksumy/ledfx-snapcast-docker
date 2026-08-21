Build a web panel for this project (ledfx-snapcast-docker), so I can start, stop and restart
each supervised process from a browser, read its logs, and edit its parameters without
recreating the container.

Work in this order:

1. Read `startup.py`, the `Dockerfile` and `docker-compose-ledfx.yaml` here first. Then read
   `app.py`, `players.py` and `static/index.html` in my reference project,
   https://github.com/shuricksumy/bluetooth-web-snapclient — the new panel should look and
   behave like that one. Fetch it if you cannot see it locally.
2. Tell me your plan before you write code, especially how you intend to split `startup.py`.
3. Implement it in small commits, each with a message explaining why.
4. Write the tests, run them, and only then tell me it is done. If you can, build the image
   and run the container to check it really comes up.

The shape of it: `startup.py` is already a supervisor (backoff, log pumping, health file) and
it is PID 1. Refactor it into a supervisor module plus a Flask app in **one process** — the
panel has to be the children's parent to signal them. Do not fork a second supervisor.
Anyone who never opens the panel must not notice any difference. The service set stays fixed
by `ROLE`; there is nothing to add or remove, the panel only drives what is already there.

Five things that will bite you:

1. The current loop restarts anything that exits. Once Stop exists that is wrong — a stopped
   service must stay stopped. Give each service a desired-state flag, and make stop atomic
   against a restart that is about to fire, or you will orphan a child process.
2. Health currently means "all services up". Stopping one on purpose must not make the
   container unhealthy; it should mean "everything that should be running is running".
3. Restarting PulseAudio breaks its clients — `autospawn = no` is deliberate, so they cannot
   respawn their own. Stop the dependents, restart PulseAudio, wait `STARTUP_DELAY_SEC`,
   start them again.
4. 8888 is LedFx's port. Put the panel on 8080 (`PANEL_PORT`) and link out to LedFx's own UI.
5. This runs behind Home Assistant Ingress, which strips a path prefix, so the page must call
   the API relative to the document:
   `const BASE = document.baseURI.replace(/[^/]*$/, "")`. Absolute paths break there.

Parameters: today's environment variables become defaults that seed `/config/services.json`,
written atomically; after that the file wins. Editing a value restarts only that service.
Cover at least the snapclient host and id, the squeezelite name, server, MAC and output, extra
args for each service, LedFx's host and port, and `PULSE_LATENCY_MSEC`. Validate anything that
reaches an argv list and return a real error rather than a service that dies at launch.

Also: a per-service log ring buffer (200 lines) in a dialog, still printed to stdout; optional
Basic auth via `ADMIN_USER` / `ADMIN_PASSWORD`; Flask from `apt` (`python3-flask`), no pip at
runtime; keep it running as uid 1000; clamp long text in table cells with an ellipsis and put
the full string in `title=`, or one long status line widens the whole table.

Leave the audio path alone — FIFOs, `PULSE_LATENCY_MSEC`'s default, `/etc/asound.conf`,
`autospawn = no`. Each has a comment explaining what broke without it. Read those before you
touch anything near them.

There is no test suite yet, so create one: pytest, fake binaries instead of real services, no
audio hardware and no network. Cover at least a crashed service being restarted with backoff,
a stopped service staying stopped, no orphan on stop, PulseAudio taking its dependents with
it, health with a deliberate stop, config surviving a restart, bad parameters rejected, and
every root `.py` being present in the Dockerfile's `COPY`. Run it in CI before the image is
pushed, and update the README and the compose example — panel port, `/config` mount, and the
`chown` it needs first.

If the code contradicts anything I have said here, trust the code and tell me what I got wrong.
