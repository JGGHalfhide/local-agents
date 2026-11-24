"""ADR 0002 candidate: plain loop on the chat-completions API, stdlib only."""
import argparse
import json
import time
import urllib.request

import common


def chat(base, key, body):
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def run(cfg, fixture):
    base, model, key = common.load_config(cfg)
    fx = common.Fixture(fixture)
    msgs = [{"role": "system", "content": common.SYSTEM_PROMPT}, {"role": "user", "content": common.USER_PROMPT}]
    opts = {"model": model, "temperature": 0, "max_tokens": common.MAX_TOKENS}
    m = {}
    for _ in range(common.MAX_TURNS):
        m = chat(base, key, {**opts, "messages": msgs, "tools": common.openai_tools()})["choices"][0]["message"]
        calls = m.get("tool_calls") or []
        if not calls:
            break
        msgs.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": [
            {**c, "function": {**c["function"], "arguments": common.sanitized(c["function"]["arguments"])}} for c in calls]})
        for c in calls:
            args = common.parse_args(c["function"]["arguments"])
            if len(fx.calls) >= common.MAX_TOOL_CALLS:
                out = "error: tool-call limit reached; give your final answer now"
            else:
                out = fx.call(c["function"]["name"], args) if args is not None else "error: arguments are not JSON"
            msgs.append({"role": "tool", "tool_call_id": c["id"], "content": out})
        m = {}               # turn cap reached with calls pending: no final text yet
    report, errs = common.load_report(m.get("content") or "")
    if report is None:      # one structured request, no tools, ending on a user turn
        if m.get("content"):
            msgs.append({"role": "assistant", "content": m["content"]})
        msgs.append({"role": "user", "content": common.FINAL_ASK})
        body = {**opts, "messages": msgs,
                "response_format": {"type": "json_schema", "json_schema": {"name": "report", "schema": common.REPORT_SCHEMA}}}
        report, errs = common.load_report(chat(base, key, body)["choices"][0]["message"]["content"])
    return report, errs, fx.calls


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--fixture", required=True)
    a = ap.parse_args()
    t = time.time()
    try:
        report, errs, calls = run(a.config, a.fixture)
        common.result_line(report=report, errors=errs, calls=calls, seconds=round(time.time() - t, 2), exception=None)
    except Exception as e:
        common.result_line(report=None, errors=[], calls=[], seconds=round(time.time() - t, 2), exception=repr(e))
