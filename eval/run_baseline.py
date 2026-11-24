#!/usr/bin/env python3
"""Week 1 baseline: the model alone (no tools, no retrieval) on eval/cases.

For each configuration, sends every case once, sequentially, to the
endpoint (local-airgap-LLM) and records the answer, latency and tokens.

  run_baseline.py --out results/week1-baseline [--configs off-greedy,...]

Reaches the KEDA interceptor with `kubectl port-forward` (needs KUBECONFIG),
sending Host: llm-api.llm.svc like an in-cluster client (same as
local-airgap-LLM's scripts/load-test.py). Resumable: cases already in a
configuration's raw.jsonl are skipped. Python stdlib + PyYAML.

Per configuration it writes <out>/<config>/raw.jsonl (one line per case:
request settings, response metadata, answer text) and answers.json (the
input for `eval/check.py score`).
"""
import argparse
import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent
HOST_HEADER = "llm-api.llm.svc"
SYSTEM = (ROOT / "prompts" / "baseline-system.txt").read_text()

# Qwen3.5-4B model card (huggingface.co/Qwen/Qwen3.5-4B, read 11/23),
# "general tasks" sets, identical in its Quickstart and Best Practices.
QWEN_INSTRUCT = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
                 "presence_penalty": 1.5}
QWEN_THINKING = {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
                 "presence_penalty": 1.5}
GREEDY = {"temperature": 0.0}
CONFIGS = {
    "off-greedy": (False, GREEDY),
    "off-qwen": (False, QWEN_INSTRUCT),
    "on-greedy": (True, GREEDY),
    "on-qwen": (True, QWEN_THINKING),
}
SCHEMA = {
    "type": "object",
    "properties": {
        "cause": {"type": "string"},
        "fix": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["cause", "fix", "evidence", "confidence"],
}
# Answer tokens; with thinking on the server caps reasoning at 1024 tokens
# (local-airgap-LLM ADR 0006) and those count as completion tokens.
MAX_TOKENS = {False: 1024, True: 2048}


def port_forward(local_port, log):
    proc = subprocess.Popen(
        ["kubectl", "-n", "keda", "port-forward",
         "svc/keda-add-ons-http-interceptor-proxy", f"{local_port}:8080"],
        stdout=log, stderr=subprocess.STDOUT, text=True)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", local_port), timeout=1).close()
            return proc
        except OSError:
            if proc.poll() is not None:
                sys.exit("port-forward exited (see its log)")
            time.sleep(0.2)
    proc.terminate()
    sys.exit("port-forward did not come up")


def post(port, body, timeout):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Host": HOST_HEADER, "Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.load(r)
    return resp, time.monotonic() - t0


def ask(port, case_input, thinking, sampling, timeout):
    body = {
        "model": "qwen",
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": case_input}],
        "max_tokens": MAX_TOKENS[thinking],
        "chat_template_kwargs": {"enable_thinking": thinking},
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "triage", "schema": SCHEMA}},
        **sampling,
    }
    resp, seconds = post(port, body, timeout)
    choice = resp["choices"][0]
    msg = choice["message"]
    content = (msg.get("content") or "").strip()
    try:
        answer = json.loads(content)
        parse_error = None
    except json.JSONDecodeError as e:
        answer, parse_error = {}, str(e)
    return {
        "seconds": round(seconds, 2),
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": resp["usage"]["prompt_tokens"],
        "completion_tokens": resp["usage"]["completion_tokens"],
        "reasoning_chars": len(msg.get("reasoning_content") or ""),
        "timings": resp.get("timings"),
        "content": content,
        "reasoning": msg.get("reasoning_content") or "",
        "answer": answer,
        "parse_error": parse_error,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--cases", help="comma-separated ids (default: all)")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--port", type=int, default=18081)
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = [yaml.safe_load(p.read_text()) for p in sorted((ROOT / "cases").glob("c*.yaml"))]
    if args.cases:
        want = set(args.cases.split(","))
        cases = [c for c in cases if c["id"] in want]
    meta = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system_prompt_sha256": hashlib.sha256(SYSTEM.encode()).hexdigest(),
        "cases": [c["id"] for c in cases],
        "configs": {k: {"thinking": v[0], "sampling": v[1], "max_tokens": MAX_TOKENS[v[0]]}
                    for k, v in CONFIGS.items() if k in args.configs.split(",")},
        "endpoint": f"interceptor via port-forward, Host: {HOST_HEADER}",
        "sequential": True,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    pf = port_forward(args.port, open(out / "port-forward.log", "a"))
    try:
        print("warm-up (cold start if the server is at zero)...", flush=True)
        post(args.port, {"model": "qwen", "max_tokens": 4, "temperature": 0,
                         "messages": [{"role": "user", "content": "Say OK."}],
                         "chat_template_kwargs": {"enable_thinking": False}}, args.timeout)
        for name in args.configs.split(","):
            thinking, sampling = CONFIGS[name]
            d = out / name
            d.mkdir(exist_ok=True)
            raw = d / "raw.jsonl"
            done = set()
            if raw.exists():
                done = {json.loads(line)["id"] for line in raw.read_text().splitlines() if line}
            for c in cases:
                if c["id"] in done:
                    continue
                try:
                    r = ask(args.port, c["input"], thinking, sampling, args.timeout)
                except Exception as e:  # noqa: BLE001 - recorded, run continues
                    r = {"error": f"{type(e).__name__}: {e}", "answer": {}}
                r = {"id": c["id"], "config": name, **r}
                with raw.open("a") as f:
                    f.write(json.dumps(r) + "\n")
                print(f"{name} {c['id']} {r.get('seconds', '-')}s "
                      f"tok={r.get('completion_tokens', '-')} finish={r.get('finish_reason', r.get('error'))}",
                      flush=True)
            answers = {}
            for line in raw.read_text().splitlines():
                r = json.loads(line)
                a = r.get("answer") or {}
                answers[r["id"]] = {"cause": str(a.get("cause", "")), "fix": str(a.get("fix", ""))}
            (d / "answers.json").write_text(json.dumps(answers, indent=2) + "\n")
    finally:
        pf.terminate()
    print("done", flush=True)


if __name__ == "__main__":
    main()
