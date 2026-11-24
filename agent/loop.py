"""The status reporter's tool loop on the openai SDK (ADR 0002).

Handles the endpoint behaviour found in the spike (ADR 0002):
- a cap on model turns (a model can call one tool hundreds of times), then
  one final request without tools;
- malformed tool-call arguments replaced before the history is resent (the
  server answers 500 for the whole conversation otherwise);
- the final structured request ends on a user turn (response_format on a
  request ending with an assistant message is rejected);
- at least one tool call before any report (the model invented a report
  when it was free to skip the tools);
- grounding: a reported fault whose namespace or name appears in no tool
  output is dropped, and listed under "ungrounded".
"""
import json
import time

from openai import OpenAI

from agent import tools

CATEGORIES = ["scaled-to-zero", "image-pull", "crash-loop", "oom-killed", "admission-denied", "unschedulable",
              "storage-unbound", "gitops-unhealthy", "node-not-ready", "other"]
MAX_TOOL_CALLS = 8
MAX_TURNS = MAX_TOOL_CALLS + 2
MAX_TOKENS = 1024

SYSTEM_PROMPT = f"""You are a read-only Kubernetes platform status reporter.
Use the tools to look at the cluster, then report every fault you find.
A fault is something broken now: a workload that should run but cannot, pods
crash-looping, OOM-killed, failing to pull, rejected at admission,
unschedulable, an unbound volume, a node not Ready.
Not faults: a workload KEDA scales to zero (the tools say so), a completed
Job, restarts in the past of a pod that is ready now. list_events already
hides warnings about objects that are healthy now.
Rules: always call tools before reporting; at most {MAX_TOOL_CALLS} tool calls; only name
namespaces and objects that appear in tool output. Each fault gets one
category from: {", ".join(CATEGORIES)}.
Your final answer is a JSON object only:
{{"faults": [{{"namespace": "...", "kind": "...", "name": "...", "category": "...",
"evidence": ["..."]}}], "summary": "..."}}
An empty "faults" list means no fault."""
USER_PROMPT = "Report the current status of the cluster: list every fault."
FINAL_ASK = "Give the final report as JSON only."
LOOK_FIRST = "Call the tools first (for example list_pods, list_workloads, list_events); do not report before."

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "faults": {"type": "array", "items": {
            "type": "object",
            "properties": {"namespace": {"type": "string"}, "kind": {"type": "string"}, "name": {"type": "string"},
                           "category": {"type": "string", "enum": CATEGORIES},
                           "evidence": {"type": "array", "items": {"type": "string"}}},
            "required": ["namespace", "kind", "name", "category", "evidence"], "additionalProperties": False}},
        "summary": {"type": "string"}},
    "required": ["faults", "summary"], "additionalProperties": False}


def parse_args(raw):
    try:
        a = json.loads(raw or "{}")
    except ValueError:
        return None
    return a if isinstance(a, dict) else None


def parse_report(text):
    s = (text or "").strip()
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j < i:
        return None
    try:
        r = json.loads(s[i:j + 1])
    except ValueError:
        return None
    if not isinstance(r, dict) or not isinstance(r.get("faults"), list) or not isinstance(r.get("summary"), str):
        return None
    ok = []
    for f in r["faults"]:
        if isinstance(f, dict) and all(isinstance(f.get(k), str) for k in ("namespace", "kind", "name", "category")) \
                and f["category"] in CATEGORIES:
            f["evidence"] = [str(e) for e in f.get("evidence") or []]
            ok.append(f)
    r["faults"] = ok
    return r


def ground(report, outputs):
    """Keep faults whose namespace (if any) and name appear in tool output."""
    seen = "\n".join(outputs)
    kept, dropped = [], []
    for f in report["faults"]:
        ns_ok = not f["namespace"] or f["namespace"] in seen
        (kept if ns_ok and f["name"] and f["name"] in seen else dropped).append(f)
    report["faults"], report["ungrounded"] = kept, dropped
    return report


def run(cfg, cluster, log=None):
    """One status report. Returns (report or None, trace)."""
    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], max_retries=1, timeout=600)
    opts = {"model": cfg["model"], "temperature": 0, "max_tokens": MAX_TOKENS}
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": USER_PROMPT}]
    trace = {"tool_calls": [], "invalid_calls": 0, "turns": 0, "looked_first_nudge": False}
    outputs, content = [], ""
    t0 = time.time()
    for _ in range(MAX_TURNS):
        trace["turns"] += 1
        m = client.chat.completions.create(messages=msgs, tools=tools.openai_tools(), **opts).choices[0].message
        content = m.content or ""
        if not m.tool_calls:
            if not trace["tool_calls"] and not trace["looked_first_nudge"]:
                trace["looked_first_nudge"] = True
                msgs += [{"role": "assistant", "content": content}, {"role": "user", "content": LOOK_FIRST}]
                continue
            break
        d = m.model_dump(exclude_none=True)
        for c in d["tool_calls"]:
            if parse_args(c["function"]["arguments"]) is None:
                c["function"]["arguments"] = "{}"
        msgs.append(d)
        for c in m.tool_calls:
            args = parse_args(c.function.arguments)
            if len(trace["tool_calls"]) >= MAX_TOOL_CALLS:
                out = "error: tool-call limit reached; give your final answer now"
            elif args is None:
                trace["invalid_calls"] += 1
                out = "error: arguments are not JSON"
            else:
                out = tools.call(cluster, c.function.name, args)
                if out.startswith("error:"):
                    trace["invalid_calls"] += 1
                trace["tool_calls"].append({"name": c.function.name, "args": args, "chars": len(out)})
                outputs.append(out)
            if log:
                log(c.function.name, args, out)
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": out})
        content = ""
    report = parse_report(content) if trace["tool_calls"] else None
    if report is None and trace["tool_calls"]:
        if content:
            msgs.append({"role": "assistant", "content": content})
        msgs.append({"role": "user", "content": FINAL_ASK})
        r = client.chat.completions.create(
            messages=msgs, response_format={"type": "json_schema", "json_schema": {"name": "report", "schema": REPORT_SCHEMA}},
            **opts)
        report = parse_report(r.choices[0].message.content)
        trace["final_structured_request"] = True
    if report is not None:
        report = ground(report, outputs)
    trace["seconds"] = round(time.time() - t0, 1)
    return report, trace
