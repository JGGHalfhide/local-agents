"""Operator API v1 (ADR 0005, docs/interface.md), standard library only.

  python -m agent serve [--port 8080]

POST /v1/status, GET /v1/runs, GET /v1/runs/{id}, GET /healthz. One run at
a time (a second POST gets 429 with Retry-After); runs are kept as JSON
files in AGENT_RUNS_DIR (an emptyDir in the cluster), the newest RUNS_KEPT.
Every run uses a fresh snapshot of the cluster.
"""
import json
import os
import pathlib
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent import __version__, k8s, loop, tools

RUNS_KEPT = 50
RUN_ID = re.compile(r"^r-\d{8}T\d{6}Z-[0-9a-f]{4}$")


class State:
    def __init__(self, cfg, runs_dir):
        self.cfg, self.dir = cfg, pathlib.Path(runs_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.running = None

    def save(self, run):
        (self.dir / f"{run['run_id']}.json").write_text(json.dumps(run))
        for old in sorted(self.dir.glob("r-*.json"))[:-RUNS_KEPT]:
            old.unlink(missing_ok=True)

    def runs(self):
        out = []
        for f in sorted(self.dir.glob("r-*.json"), reverse=True):
            try:
                r = json.loads(f.read_text())
            except (OSError, ValueError):
                continue
            out.append({"run_id": r["run_id"], "started": r["timings"]["started"], "status": r["status"],
                        "namespace": r["namespace"], "findings": len(r["findings"]),
                        "seconds": r["timings"]["total_s"], "demo": r.get("demo", False)})
        return out

    def get(self, run_id):
        f = self.dir / f"{run_id}.json"
        return json.loads(f.read_text()) if RUN_ID.match(run_id) and f.exists() else None


def make_handler(state):
    class H(BaseHTTPRequestHandler):
        server_version = f"local-agents/{__version__}"

        def log_message(self, fmt, *args):     # one line per request, to stderr (Loki)
            print(json.dumps({"method": self.command, "path": self.path, "status": args[1] if len(args) > 1 else ""}),
                  flush=True)

        def send(self, code, body, headers=None):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/healthz":
                return self.send(200, {"ok": True, "version": __version__, "busy": state.running is not None,
                                       "runs_kept": len(list(state.dir.glob("r-*.json")))})
            if self.path == "/v1/runs":
                return self.send(200, state.runs())
            m = re.fullmatch(r"/v1/runs/([^/]+)", self.path)
            if m:
                r = state.get(m.group(1))
                return self.send(200, r) if r else self.send(404, {"error": "no such run"})
            return self.send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/status":
                return self.send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > 4096:
                return self.send(400, {"error": "body too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self.send(400, {"error": "body is not JSON"})
            if not isinstance(body, dict) or set(body) - {"namespace", "thinking"}:
                return self.send(400, {"error": "allowed fields: namespace, thinking"})
            ns, thinking = body.get("namespace"), body.get("thinking", False)
            if ns is not None and (not isinstance(ns, str) or not re.fullmatch(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?", ns)):
                return self.send(400, {"error": "namespace must be a namespace name or null"})
            if not isinstance(thinking, bool):
                return self.send(400, {"error": "thinking must be true or false"})
            if not state.lock.acquire(blocking=False):
                return self.send(429, {"error": "busy", "run_id": state.running}, {"Retry-After": "30"})
            try:
                state.running = loop.new_run_id()
                run = loop.run(state.cfg, tools.Cluster(k8s.source()), namespace=ns, thinking=thinking,
                               run_id=state.running)
                state.save(run)
            finally:
                state.running = None
                state.lock.release()
            return self.send(504 if run["error"] == "deadline exceeded" else 200, run)

    return H


def serve(cfg, port=8080, runs_dir=None):
    state = State(cfg, runs_dir or os.environ.get("AGENT_RUNS_DIR", "/var/lib/agent/runs"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), make_handler(state))
    print(json.dumps({"listening": port, "version": __version__, "runs_dir": str(state.dir)}), flush=True)
    srv.serve_forever()
