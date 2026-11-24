"""ADR 0002 candidate: plain loop on the official openai SDK."""
import argparse
import json
import time

from openai import OpenAI

import common


def run(cfg, fixture):
    base, model, key = common.load_config(cfg)
    client = OpenAI(base_url=base, api_key=key, max_retries=0, timeout=600)
    fx = common.Fixture(fixture)
    msgs = [{"role": "system", "content": common.SYSTEM_PROMPT}, {"role": "user", "content": common.USER_PROMPT}]
    opts = {"model": model, "temperature": 0, "max_tokens": common.MAX_TOKENS}
    content = ""
    for _ in range(common.MAX_TURNS):
        m = client.chat.completions.create(messages=msgs, tools=common.openai_tools(), **opts).choices[0].message
        content = m.content or ""
        if not m.tool_calls:
            break
        d = m.model_dump(exclude_none=True)
        for c in d["tool_calls"]:
            c["function"]["arguments"] = common.sanitized(c["function"]["arguments"])
        msgs.append(d)
        for c in m.tool_calls:
            args = common.parse_args(c.function.arguments)
            if len(fx.calls) >= common.MAX_TOOL_CALLS:
                out = "error: tool-call limit reached; give your final answer now"
            else:
                out = fx.call(c.function.name, args) if args is not None else "error: arguments are not JSON"
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": out})
        content = ""         # turn cap reached with calls pending: no final text yet
    report, errs = common.load_report(content)
    if report is None:      # one structured request, no tools, ending on a user turn
        if content:
            msgs.append({"role": "assistant", "content": content})
        msgs.append({"role": "user", "content": common.FINAL_ASK})
        r = client.chat.completions.create(
            messages=msgs, response_format={"type": "json_schema", "json_schema": {"name": "report", "schema": common.REPORT_SCHEMA}}, **opts)
        report, errs = common.load_report(r.choices[0].message.content or "")
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
