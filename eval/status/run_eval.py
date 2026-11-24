#!/usr/bin/env python3
"""Fault-injection eval of the status reporter, through the operator API
(ADR 0005: the scorer uses the operators' path).

  KUBECONFIG=... eval/status/run_eval.py <results-dir> [--cases f04,k3,...]

For each case, one at a time: eval/status/inject.sh <id> (waits until the
case is visible) -> POST /v1/status (whole cluster) through
`kubectl -n agents port-forward svc/status-reporter` -> save the run object
as <results-dir>/<id>.json -> eval/status/cleanup.sh <id>. Then
eval/status/score.py. Cleanup runs even if a step fails. Retries once after
Retry-After on 429 (a scheduled run in progress). Run detached: about 2-5
minutes per case.
"""
import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
CASES = ["f01", "f02", "f04", "f05", "f06", "f07", "f08", "f10", "k1", "k2", "k3", "k4", "k5"]
PORT = 18200


def status(timeout=330):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/status", method="POST",
                                 data=json.dumps({"namespace": None, "thinking": False}).encode(),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(int(e.headers.get("Retry-After", "30")) + 5)
                continue
            body = e.read()
            try:
                return e.code, json.loads(body)
            except ValueError:
                return e.code, {"error": body[:300].decode(errors="replace")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--cases", default=",".join(CASES))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pf = subprocess.Popen(["kubectl", "-n", "agents", "port-forward", "svc/status-reporter", f"{PORT}:8080"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = open(out / "run.log", "a")

    def say(msg):
        line = f"{dt.datetime.now(dt.UTC):%H:%M:%S} {msg}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    try:
        time.sleep(3)
        for cid in a.cases.split(","):
            try:
                inj = subprocess.run([str(ROOT / "eval/status/inject.sh"), cid], capture_output=True, text=True)
                say(f"{cid}: inject exit {inj.returncode} {inj.stdout.strip().splitlines()[-1] if inj.stdout.strip() else ''}"
                    f"{(' ' + inj.stderr.strip()) if inj.returncode else ''}")
                if inj.returncode != 0:
                    continue
                code, run = status()
                (out / f"{cid}.json").write_text(json.dumps(run, indent=1) + "\n")
                say(f"{cid}: HTTP {code} status={run.get('status')} findings="
                    f"{[(f['namespace'], f['object'], f['category']) for f in run.get('findings') or []]} "
                    f"{run.get('timings', {}).get('total_s')}s error={run.get('error')}")
            finally:
                cl = subprocess.run([str(ROOT / "eval/status/cleanup.sh"), cid], capture_output=True, text=True)
                say(f"{cid}: cleanup exit {cl.returncode} {cl.stdout.strip().splitlines()[-1] if cl.stdout.strip() else ''}")
    finally:
        pf.terminate()
    subprocess.run([sys.executable, str(ROOT / "eval/status/score.py"), str(out)])


if __name__ == "__main__":
    main()
