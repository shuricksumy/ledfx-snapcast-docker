#!/usr/bin/env python3
"""The web panel: HTTP in front of the supervisor, nothing more.

It owns no processes. Every action posts an intent to the supervisor loop and
waits briefly for it to land, so a request cannot race the loop over a child.
"""
import hmac
import os
import threading

from flask import Flask, jsonify, request, send_from_directory

import services
from services import ConfigError
from supervisor import log

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
PANEL_PORT = int(os.environ.get("PANEL_PORT", "8080"))
PANEL_HOST = os.environ.get("PANEL_HOST", "0.0.0.0")

# How long an action waits for the supervisor loop to carry out its intent
# before answering anyway. Stopping a stubborn child can take STOP_GRACE_S, and
# the browser should not sit on a dead request that long - the next poll shows
# the outcome.
INTENT_TIMEOUT = 3.0


def create_app(sup, doc, snapserver_config=None):
    here = os.path.dirname(os.path.abspath(__file__))
    app = Flask(__name__, static_folder=os.path.join(here, "static"), static_url_path="")
    state = {"doc": doc}
    lock = threading.Lock()

    @app.before_request
    def require_auth():
        """Gate everything - API and page - when ADMIN_PASSWORD is set.

        Unset means no auth, which is why the README says this belongs on a
        trusted LAN rather than a port forward.
        """
        if not ADMIN_PASSWORD:
            return None
        auth = request.authorization
        if (
            auth
            and auth.type == "basic"
            and hmac.compare_digest(auth.username or "", ADMIN_USER)
            and hmac.compare_digest(auth.password or "", ADMIN_PASSWORD)
        ):
            return None
        return (
            jsonify(error="authentication required"),
            401,
            {"WWW-Authenticate": 'Basic realm="ledfx-snapcast"'},
        )

    @app.errorhandler(ConfigError)
    def bad_config(exc):
        return jsonify(error=str(exc)), 400

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/config")
    def api_config():
        doc = state["doc"]
        return jsonify(
            role=doc["role"],
            auth=bool(ADMIN_PASSWORD),
            services=doc["services"],
            env=doc["env"],
            managed=list(services.ROLE_SERVICES[doc["role"]]),
            # So the page can link out to LedFx's own UI on its real port
            # rather than assuming 8888.
            ledfx_port=doc["services"]["ledfx"]["port"] if doc["role"] == "ledfx-suite" else None,
        )

    @app.patch("/api/config")
    def api_patch_config():
        with lock:
            new_doc, changed = services.apply_patch(state["doc"], request.get_json(silent=True) or {})
            # Build before saving: an argv that cannot be constructed should be
            # a 400, not a config file that breaks the next boot.
            specs = services.build(new_doc, fifo_dir=new_doc["env"].get("FIFO_DIR", "/tmp"),
                                   config_file=snapserver_config)
            services.save(new_doc)
            state["doc"] = new_doc
            if changed:
                log("INFO", "⚙️ Applying config change to: %s" % ", ".join(changed))
                sup.reconfigure(specs, changed).wait(INTENT_TIMEOUT)
        return jsonify(ok=True, changed=changed, services=new_doc["services"], env=new_doc["env"])

    @app.post("/api/config/reset")
    def api_reset_config():
        with lock:
            doc = services.reset_to_env(role=state["doc"]["role"])
            specs = services.build(doc, fifo_dir=doc["env"].get("FIFO_DIR", "/tmp"),
                                   config_file=snapserver_config)
            state["doc"] = doc
            sup.reconfigure(specs, list(specs)).wait(INTENT_TIMEOUT)
        return jsonify(ok=True, services=doc["services"], env=doc["env"])

    @app.get("/api/services")
    def api_services():
        return jsonify(services=sup.status(), healthy=sup.healthy())

    @app.post("/api/services/<name>/<action>")
    def api_action(name, action):
        if name not in sup.services:
            return jsonify(error="unknown service %s" % name), 404
        fn = {"start": sup.start, "stop": sup.stop, "restart": sup.restart}.get(action)
        if fn is None:
            return jsonify(error="unknown action %s" % action), 400
        log("INFO", "🖐️ Panel requested %s of %s" % (action, name))
        fn(name).wait(INTENT_TIMEOUT)
        return jsonify(ok=True, service=sup.services[name].status())

    @app.get("/api/services/<name>/logs")
    def api_logs(name):
        svc = sup.services.get(name)
        if svc is None:
            return jsonify(error="unknown service %s" % name), 404
        return jsonify(name=name, logs=list(svc.logs))

    @app.get("/api/health")
    def api_health():
        healthy = sup.healthy()
        return jsonify(healthy=healthy), (200 if healthy else 503)

    return app


def serve(sup, doc, snapserver_config=None):
    app = create_app(sup, doc, snapserver_config)
    if not ADMIN_PASSWORD:
        log("WARN", "🔓 ADMIN_PASSWORD is unset - the panel is open to anyone who can reach it")
    log("INFO", "🌐 Panel listening on %s:%s" % (PANEL_HOST, PANEL_PORT))
    # make_server rather than app.run: app.run prints Werkzeug's development
    # server banner and "Press CTRL+C to quit" into the container log, which is
    # noise at best and alarming at worst next to the audio logs. threaded so a
    # slow stop does not queue the status poll behind it; no reloader, since
    # this is a thread of PID 1 and a reloader would fork.
    from werkzeug.serving import make_server

    make_server(PANEL_HOST, PANEL_PORT, app, threaded=True).serve_forever()
