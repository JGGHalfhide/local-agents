#!/usr/bin/env python3
"""agentctl: command-line client for the status reporter's API v1
(ADR 0005, docs/interface.md). Python standard library only.

  agentctl status [-n NAMESPACE] [--thinking]
  agentctl runs
  agentctl trace RUN_ID
  agentctl health

  --json         print the API's JSON unchanged
  --timeout S    seconds to wait (default 330: the server's 300 s run limit + margin)
  --endpoint URL default $AGENTCTL_ENDPOINT, else http://127.0.0.1:8080
                 (kubectl -n agents port-forward svc/status-reporter 8080:8080)

Exit codes: 0 healthy, 1 fault found, 2 error or unknown. runs, trace and
health: 0 on success, 2 on error.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

OK, FAULT, ERROR = 0, 1, 2


def request(endpoint, method, path, body=None, timeout=330):
    req = urllib.request.Request(endpoint.rstrip("/") + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e), dict(e.headers)
        except ValueError:
            return e.code, {"error": e.reason}, dict(e.headers)


def print_run(run):
    mark = {"healthy": "HEALTHY", "fault": "FAULT", "unknown": "UNKNOWN"}.get(run["status"], run["status"])
    scope = run["namespace"] or "whole cluster"
    t = run["timings"]
    print(f"{mark}  {run['run_id']}  ({scope}, {t['total_s']} s, {len(run['tool_calls'])} tool calls, "
          f"model {run['model']['name']}{', thinking' if run['model']['thinking'] else ''})"
          + ("  [DEMO: recorded run]" if run.get("demo") else ""))
    if run.get("error"):
        print(f"error: {run['error']}")
    calls = {c["id"]: c for c in run["tool_calls"]}
    for i, f in enumerate(run["findings"], 1):
        print(f"\n{i}. {f['category']}  {f['namespace'] + '/' if f['namespace'] else ''}{f['object']}")
        if f.get("summary"):
            print(f"   {f['summary']}")
        for e in f["evidence"]:
            c = calls.get(e["tool_call_id"], {})
            args = json.dumps(c.get("arguments", {})) if c.get("arguments") else ""
            print(f"   evidence {e['tool_call_id']} {c.get('tool', '?')}{args}: {e['excerpt']}")
    if run["ungrounded"]:
        print("\nDropped (not reported):")
        for u in run["ungrounded"]:
            print(f"   {u['category']}  {u['namespace']}/{u['object']}: {u['reason']}")
    if run["status"] == "healthy":
        print("\nNo faults found.")
    if run.get("summary"):
        print(f"\nModel summary: {run['summary']}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agentctl", description="Client for the status reporter API v1.")
    ap.add_argument("--json", action="store_true", help="print the API's JSON unchanged")
    ap.add_argument("--timeout", type=float, default=330)
    ap.add_argument("--endpoint", default=os.environ.get("AGENTCTL_ENDPOINT", "http://127.0.0.1:8080"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="run the status reporter now")
    st.add_argument("-n", "--namespace")
    st.add_argument("--thinking", action="store_true", help="opt in to thinking (untested until Week 4)")
    sub.add_parser("runs", help="list recent runs")
    tr = sub.add_parser("trace", help="every tool call of one run")
    tr.add_argument("run_id")
    sub.add_parser("health", help="is the server up")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return ERROR if e.code else OK
    try:
        if a.cmd == "status":
            code, body, headers = request(a.endpoint, "POST", "/v1/status",
                                          {"namespace": a.namespace, "thinking": a.thinking}, a.timeout)
        elif a.cmd == "runs":
            code, body, headers = request(a.endpoint, "GET", "/v1/runs", timeout=a.timeout)
        elif a.cmd == "trace":
            code, body, headers = request(a.endpoint, "GET", f"/v1/runs/{a.run_id}", timeout=a.timeout)
        else:
            code, body, headers = request(a.endpoint, "GET", "/healthz", timeout=a.timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        print(f"agentctl: cannot reach {a.endpoint}: {e}", file=sys.stderr)
        return ERROR
    if a.json:
        print(json.dumps(body, indent=1))
    if code == 429:
        if not a.json:
            print(f"busy: run {body.get('run_id')} in progress; retry after {headers.get('Retry-After', '30')} s",
                  file=sys.stderr)
        return ERROR
    if code not in (200, 504):
        if not a.json:
            print(f"agentctl: HTTP {code}: {body.get('error', body)}", file=sys.stderr)
        return ERROR
    if a.cmd == "status":
        if not a.json:
            print_run(body)
        return {"healthy": OK, "fault": FAULT}.get(body.get("status"), ERROR)
    if not a.json:
        if a.cmd == "runs":
            print(f"{'RUN':<28} {'STARTED':<21} {'STATUS':<8} {'FINDINGS':>8} {'SECONDS':>8}  SCOPE")
            for r in body:
                print(f"{r['run_id']:<28} {r['started']:<21} {r['status']:<8} {r['findings']:>8} {r['seconds']:>8}  "
                      f"{r['namespace'] or '-'}{'  DEMO' if r.get('demo') else ''}")
        elif a.cmd == "trace":
            print_run(body)
            print("\nTool calls:")
            for c in body["tool_calls"]:
                print(f"\n{c['id']} {c['tool']} {json.dumps(c['arguments'])}  {c['duration_ms']} ms"
                      f"{'  ERROR' if c['error'] else ''}  ({c['result_chars']} chars"
                      f"{', truncated' if c['truncated'] else ''})")
                print("   " + c["result"].replace("\n", "\n   "))
        else:
            print(f"{'up' if body.get('ok') else 'DOWN'}, version {body.get('version')}, "
                  f"{'busy' if body.get('busy') else 'idle'}, {body.get('runs_kept')} runs kept")
    return OK


if __name__ == "__main__":
    sys.exit(main())
