#!/usr/bin/env python3
"""Nightcraft Runtime Manager.

An always-on daemon (127.0.0.1:5700, run as root) that owns the lifecycle
of `on_demand` products built on systemd. For each on_demand product:

  * GET/POST /touch/<slug>  -> record last_access[slug]=now; if the service is
                                 inactive and not already starting, spawn a
                                 background thread that runs `systemctl start`.
  * GET       /healthz       -> liveness check.
  * background sweep every 30s: for each active on_demand service whose idle
                                 window has elapsed, `systemctl stop` it.

last_access is persisted to /runtime/nightcraft/manager/last_access.json so a
manager restart can re-seed timers for services that are already running.

Standard library only (http.server, threading, subprocess, yaml).
"""

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MANIFEST_PATH = os.environ.get("NC_PRODUCTS_YML", "/etc/nightcraft/products.yml")
STATE_DIR = "/runtime/nightcraft/manager"
STATE_FILE = os.path.join(STATE_DIR, "last_access.json")
MANAGER_PORT = 5700

try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML is required (apt-get install python3-yaml)\n")
    sys.exit(1)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("[runtime-manager] %s %s" % (ts, msg), flush=True)


def _now_seconds():
    return int(time.time())


def parse_idle_timeout(value):
    """Parse '15m' / '1h' / '1d' (or a bare seconds int) into seconds."""
    value = str(value).strip()
    if not value:
        return 0
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = value[-1].lower()
    if unit in mult:
        try:
            return int(value[:-1]) * mult[unit]
        except ValueError:
            return 0
    try:
        return int(value)
    except ValueError:
        return 0


def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        log("Manifest missing: %s" % MANIFEST_PATH)
        return {}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("products", {}) or {}


def on_demand_products(products):
    out = {}
    for slug, product in products.items():
        rt = product.get("runtime") or {}
        if rt.get("policy") == "on_demand":
            out[slug] = product
    return out


def systemctl(args):
    cmd = ["systemctl"] + list(args)
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        log("systemctl %s timed out" % " ".join(args))
        return 1, "", "timeout"
    except Exception as exc:  # noqa: BLE001
        log("systemctl %s failed: %s" % (" ".join(args), exc))
        return 1, "", str(exc)


def is_active(service):
    rc, out, _ = systemctl(["is-active", service])
    return rc == 0 and out == "active"


class Manager:
    def __init__(self):
        self.lock = threading.Lock()
        self.last_access = {}
        self.starting = set()
        self.products = {}
        self.od_products = {}
        self.load_products()
        self.load_state()
        self.seed_active()
        self.persist()

    def load_products(self):
        self.products = load_manifest()
        self.od_products = on_demand_products(self.products)

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as fh:
                    self.last_access = json.load(fh)
            except Exception:  # noqa: BLE001
                self.last_access = {}

    def persist(self):
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.last_access, fh)
        except Exception as exc:  # noqa: BLE001
            log("Failed to persist state: %s" % exc)

    def seed_active(self):
        now = _now_seconds()
        for slug, product in self.od_products.items():
            service = product["runtime"]["service"]
            if is_active(service):
                self.last_access[slug] = now
                log("Seeded active on_demand service %s (%s)" % (slug, service))

    def touch(self, slug):
        product = self.od_products.get(slug)
        if product is None:
            return False
        service = product["runtime"]["service"]
        with self.lock:
            self.last_access[slug] = _now_seconds()
            should_start = slug not in self.starting and not is_active(service)
            if should_start:
                self.starting.add(slug)
        if should_start:
            log("Touch %s: service inactive, starting %s" % (slug, service))
            threading.Thread(
                target=self._start_worker, args=(slug, service), daemon=True
            ).start()
        self.persist()
        return True

    def _start_worker(self, slug, service):
        rc, _, err = systemctl(["start", service])
        with self.lock:
            self.starting.discard(slug)
        if rc == 0:
            log("Started %s (%s)" % (slug, service))
        else:
            log("Failed to start %s (%s): %s" % (slug, service, err))

    def sweep(self):
        now = _now_seconds()
        for slug, product in self.od_products.items():
            rt = product["runtime"]
            service = rt["service"]
            idle = parse_idle_timeout(rt.get("idle_timeout", "15m"))
            if idle <= 0:
                continue
            with self.lock:
                last = self.last_access.get(slug, now)
            if not is_active(service):
                continue
            if (now - last) > idle:
                log("Idle timeout for %s (%s); stopping" % (slug, service))
                systemctl(["stop", service])
                with self.lock:
                    self.last_access.pop(slug, None)
        self.persist()


def run_sweep(manager):
    while True:
        time.sleep(30)
        try:
            manager.sweep()
        except Exception as exc:  # noqa: BLE001
            log("Sweep error: %s" % exc)


class Handler(BaseHTTPRequestHandler):
    manager = None

    def _send(self, code, body=""):
        self.send_response(code)
        if body:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body.encode("utf-8"))))
        self.end_headers()
        if body:
            self.wfile.write(body.encode("utf-8"))

    def log_message(self, fmt, *args):
        log("%s - %s" % (self.address_string(), fmt % args))

    def do_GET(self):
        self.handle_route()

    def do_POST(self):
        self.handle_route()

    def handle_route(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        if path == "/healthz":
            self._send(200, "ok\n")
            return
        if path.startswith("/touch/"):
            slug = path[len("/touch/"):]
            if not slug:
                self._send(400, "missing slug\n")
                return
            if self.server.manager.touch(slug):  # noqa: E501
                self._send(202, "touched %s\n" % slug)
            else:
                self._send(404, "unknown on_demand product\n")
            return
        self._send(404, "not found\n")


def main():
    os.makedirs(STATE_DIR, exist_ok=True)
    manager = Manager()
    sweep_thread = threading.Thread(target=run_sweep, args=(manager,), daemon=True)
    sweep_thread.start()

    server = ThreadingHTTPServer(("127.0.0.1", MANAGER_PORT), Handler)
    server.manager = manager
    log("Runtime manager listening on 127.0.0.1:%d" % MANAGER_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
