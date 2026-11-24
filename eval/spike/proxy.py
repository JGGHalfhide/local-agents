#!/usr/bin/env python3
"""Logging proxy for the ADR 0002 spike (stdlib only).

  proxy.py <listen-port> <upstream-base> [<host-header>]

Forwards every request to <upstream-base> (e.g. http://127.0.0.1:18081, the
port-forward to the KEDA interceptor) and appends one JSON line per
request/response to the current log, so every candidate is measured the
same way: the tool calls the model actually emitted, token usage and
llama-server timings, whatever the framework does with them. <host-header>
(llm-api.llm.svc) is what the interceptor routes on; in-cluster clients send
it anyway, so the candidates' config stays a plain base URL.

Control: POST /__run with {"log": "<path>", "run": "<id>"} switches the log.
"""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, UPSTREAM = int(sys.argv[1]), sys.argv[2].rstrip("/")
HOST = sys.argv[3] if len(sys.argv) > 3 else None
STATE = {"log": None, "run": None}
LOCK = threading.Lock()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_GET(self):
        self._forward(b"")

    def do_POST(self):
        body = self._body()
        if self.path == "/__run":
            STATE.update(json.loads(body))
            self.send_response(204)
            self.end_headers()
            return
        self._forward(body)

    def _forward(self, body):
        hdrs = {k: v for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length", "connection", "accept-encoding")}
        if HOST:
            hdrs["Host"] = HOST
        req = urllib.request.Request(UPSTREAM + self.path, data=body or None, headers=hdrs, method=self.command)
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                status, data, ctype = r.status, r.read(), r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, data, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
        except Exception as e:  # upstream down: report it to the client as 502
            status, data, ctype = 502, json.dumps({"error": str(e)}).encode(), "application/json"
        dt = time.time() - t0
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        if STATE["log"]:
            try:
                req_j = json.loads(body) if body else None
            except ValueError:
                req_j = {"raw": body[:2000].decode(errors="replace")}
            try:
                resp_j = json.loads(data)
            except ValueError:
                resp_j = {"raw": data[:20000].decode(errors="replace")}
            rec = {"run": STATE["run"], "t": round(t0, 3), "seconds": round(dt, 3), "path": self.path,
                   "status": status, "request": req_j, "response": resp_j}
            with LOCK, open(STATE["log"], "a") as f:
                f.write(json.dumps(rec) + "\n")


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
