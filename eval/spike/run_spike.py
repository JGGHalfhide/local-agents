#!/usr/bin/env python3
"""ADR 0002 spike orchestrator (stdlib only).

  KUBECONFIG=... run_spike.py <out-dir> [--runs N] [--candidates a,b] [--fixtures x,y]

Starts `kubectl port-forward` to the KEDA interceptor (as eval/run_baseline.py
does) and the logging proxy (proxy.py) in front of it, then runs every
candidate x fixture N times, sequentially, each in its own venv from
scripts/runtime-footprint.sh (build/runtime-footprint/<name>/venv, the pinned
versions of docs/scans/week1-runtime-footprint.txt). Writes:

  <out-dir>/runs.jsonl    one line per run: candidate, fixture, i, result
  <out-dir>/proxy.jsonl   every request/response through the proxy
  <out-dir>/meta.json     versions, config, caps, egress trap

Egress trap: every run gets HTTP(S)_PROXY/ALL_PROXY=http://127.0.0.1:9
(nothing listens) with NO_PROXY=127.0.0.1,localhost, so a library that tries
to reach the internet over HTTP fails visibly instead of silently. Raw
sockets would bypass it; it is a check, not a firewall.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
VENVS = ROOT / "build" / "runtime-footprint"
CANDIDATES = {"plain-stdlib": "run_stdlib.py", "plain-openai": "run_openai.py",
              "pydantic-ai": "run_pydantic_ai.py", "langgraph": "run_langgraph.py",
              "smolagents": "run_smolagents.py"}
FIXTURES = ["healthy", "f04-crash-loop", "f06-admission-denied", "k1-keda-zero"]
PF_PORT, PROXY_PORT = 18081, 18090
RUN_TIMEOUT = 900          # seconds per run; a stuck run is recorded as failed


def wait_port(url, tries=60):
    for _ in range(tries):
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception as e:
            if getattr(e, "code", None):
                return True
            time.sleep(1)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--candidates", default=",".join(CANDIDATES))
    ap.add_argument("--fixtures", default=",".join(FIXTURES))
    ap.add_argument("--pairs", help="only these candidate:fixture pairs, comma-separated (reruns)")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cands, fixtures = a.candidates.split(","), a.fixtures.split(",")
    pairs = {tuple(p.split(":")) for p in a.pairs.split(",")} if a.pairs else None
    pf = subprocess.Popen(["kubectl", "-n", "keda", "port-forward", "svc/keda-add-ons-http-interceptor-proxy",
                           f"{PF_PORT}:8080"], stdout=open(out / "port-forward.log", "w"), stderr=subprocess.STDOUT)
    px = subprocess.Popen([sys.executable, str(HERE / "proxy.py"), str(PROXY_PORT), f"http://127.0.0.1:{PF_PORT}",
                           "llm-api.llm.svc"])
    try:
        if not wait_port(f"http://127.0.0.1:{PROXY_PORT}/health", 90):
            sys.exit("endpoint not reachable through port-forward + proxy")
        tiktoken_cache = out / "tiktoken-cache"
        tiktoken_cache.mkdir(exist_ok=True)
        env = dict(os.environ, HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9",
                   ALL_PROXY="http://127.0.0.1:9", NO_PROXY="127.0.0.1,localhost",
                   http_proxy="http://127.0.0.1:9", https_proxy="http://127.0.0.1:9",
                   no_proxy="127.0.0.1,localhost", TIKTOKEN_CACHE_DIR=str(tiktoken_cache),
                   PYTHONPATH=str(HERE), PYTHONDONTWRITEBYTECODE="1")
        meta = {"started": dt.datetime.now(dt.UTC).isoformat(), "runs_per_fixture": a.runs,
                "candidates": cands, "fixtures": fixtures, "config": json.loads((HERE / "config.lab.json").read_text()),
                "caps": {"max_tool_calls": 8, "max_result_chars": 3500, "max_tokens": 512, "temperature": 0, "thinking": "server default (off)"},
                "python": {c: subprocess.run([str(VENVS / c / "venv/bin/python"), "--version"], capture_output=True, text=True).stdout.strip() for c in cands},
                "egress_trap": "HTTP(S)_PROXY/ALL_PROXY=http://127.0.0.1:9, NO_PROXY=127.0.0.1,localhost"}
        (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
        for i in range(a.runs):              # rounds: all candidates per round, so drift spreads evenly
            for fx in fixtures:
                for c in cands:
                    if pairs is not None and (c, fx) not in pairs:
                        continue
                    run_id = f"{c}/{fx}/{i}"
                    req = urllib.request.Request(f"http://127.0.0.1:{PROXY_PORT}/__run", method="POST",
                                                 data=json.dumps({"log": str(out / "proxy.jsonl"), "run": run_id}).encode())
                    urllib.request.urlopen(req, timeout=5)
                    t = time.time()
                    cmd = [str(VENVS / c / "venv/bin/python"), str(HERE / CANDIDATES[c]),
                           "--config", str(HERE / "config.lab.json"),
                           "--fixture", str(HERE / "fixtures" / f"{fx}.json")]
                    try:
                        p = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=RUN_TIMEOUT)
                        code, stdout, stderr = p.returncode, p.stdout, p.stderr
                    except subprocess.TimeoutExpired as e:   # a stuck run fails; the spike goes on
                        out_ = e.stdout or ""
                        stdout = out_.decode(errors="replace") if isinstance(out_, bytes) else out_
                        code, stderr = "timeout", f"timed out after {RUN_TIMEOUT} s"
                    res = next((json.loads(l[7:]) for l in stdout.splitlines() if l.startswith("RESULT ")), None)
                    if res is None and code == "timeout":
                        res = {"report": None, "errors": [], "calls": [], "seconds": RUN_TIMEOUT,
                               "exception": f"run timed out after {RUN_TIMEOUT} s"}
                    # Repo-relative paths: tracebacks and warnings carry the
                    # absolute path, which names the user's home directory.
                    stderr = stderr.replace(str(ROOT) + "/", "").replace(str(pathlib.Path.home()), "~")
                    rec = {"run": run_id, "candidate": c, "fixture": fx, "i": i, "exit": code,
                           "wall_seconds": round(time.time() - t, 2), "result": res,
                           "stderr_tail": stderr[-3000:]}
                    with open(out / "runs.jsonl", "a") as f:
                        f.write(json.dumps(rec) + "\n")
                    print(f"{run_id}: exit {p.returncode} {rec['wall_seconds']}s "
                          f"calls={len((res or {}).get('calls') or [])} report={'ok' if (res or {}).get('report') else 'NONE'} "
                          f"exc={(res or {}).get('exception')}", flush=True)
        meta["finished"] = dt.datetime.now(dt.UTC).isoformat()
        meta["tiktoken_cache_files"] = sorted(p.name for p in tiktoken_cache.iterdir())
        (out / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    finally:
        px.terminate()
        pf.terminate()


if __name__ == "__main__":
    main()
