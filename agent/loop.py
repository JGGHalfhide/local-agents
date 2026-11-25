"""The status reporter's tool loop on the openai SDK (ADR 0002); returns the
run object of the operator API (ADR 0005, docs/interface.md).

Handles the endpoint behaviour found in the spike (ADR 0002):
- a cap on model turns (a model can call one tool hundreds of times), then
  one final request without tools;
- malformed tool-call arguments replaced before the history is resent (the
  server answers 500 for the whole conversation otherwise);
- the final structured request ends on a user turn (response_format on a
  request ending with an assistant message is rejected);
- at least one tool call before any report (the model invented a report
  when it was free to skip the tools).
Then, on the model's report:
- evidence: each quote is matched to the tool call whose result contains
  it; a finding with no matching quote gets the tool-result line naming its
  object;
- grounding (the scorer's check): a finding whose namespace or name appears
  in no tool result is moved to "ungrounded";
- the KEDA rule (step 3 smoke test): a scaled-to-zero finding on a workload
  KEDA manages is moved to "ungrounded".
"""
import datetime as dt
import hashlib
import json
import re
import secrets
import time

from openai import OpenAI

from opentelemetry.trace import Status, StatusCode

from agent import tools, tracing

CATEGORIES = ["scaled-to-zero", "image-pull", "crash-loop", "oom-killed", "admission-denied", "unschedulable",
              "storage-unbound", "gitops-unhealthy", "node-not-ready", "other"]
MAX_TOOL_CALLS = 8
MAX_TURNS = MAX_TOOL_CALLS + 2
MAX_TOKENS = 1024
DEADLINE_S = 300
RESULT_KEEP = 2000

SYSTEM_PROMPT = f"""You are a read-only Kubernetes platform status reporter.
Use the tools to look at the cluster, then report every fault you find.
A fault is something broken now: a workload that should run but cannot, pods
crash-looping, OOM-killed, failing to pull, rejected at admission,
unschedulable, an unbound volume, a node not Ready, a Service whose workload
was scaled to zero by hand, an Argo CD application not Synced or not Healthy.
Not faults: a workload KEDA scales to zero (the tools say so), a completed
Job, restarts in the past of a pod that is ready now. list_events already
hides warnings about objects that are healthy now.
Start with the overview tool; use the other tools only to look closer at
something it shows. Rules: always call tools before reporting; at most {MAX_TOOL_CALLS} tool calls; only name
namespaces and objects that appear in tool output; quote evidence exactly as
the tools printed it. Each fault gets one category from:
{", ".join(CATEGORIES)}.
Your final answer is a JSON object only:
{{"faults": [{{"namespace": "...", "kind": "...", "name": "...", "category": "...",
"summary": "one sentence", "evidence": ["exact text from a tool result"]}}], "summary": "..."}}
An empty "faults" list means no fault."""
USER_PROMPT = "Report the current status of the cluster: list every fault."
FINAL_ASK = "Give the final report as JSON only."
LOOK_FIRST = "Call the tools first (start with overview); do not report before."
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "faults": {"type": "array", "items": {
            "type": "object",
            "properties": {"namespace": {"type": "string"}, "kind": {"type": "string"}, "name": {"type": "string"},
                           "category": {"type": "string", "enum": CATEGORIES}, "summary": {"type": "string"},
                           "evidence": {"type": "array", "items": {"type": "string"}}},
            "required": ["namespace", "kind", "name", "category", "evidence"], "additionalProperties": False}},
        "summary": {"type": "string"}},
    "required": ["faults", "summary"], "additionalProperties": False}

NS_TOOLS = {n for n, _d, props, _r in tools.SPECS if "namespace" in props}


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
    if not isinstance(r, dict) or not isinstance(r.get("faults"), list):
        return None
    faults = [f for f in r["faults"] if isinstance(f, dict)
              and all(isinstance(f.get(k), str) for k in ("namespace", "kind", "name", "category"))
              and f["category"] in CATEGORIES]
    return {"faults": faults, "summary": r.get("summary") if isinstance(r.get("summary"), str) else ""}


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def _evidence(fault, calls):
    """Evidence items {tool_call_id, excerpt}: the model's quotes found verbatim
    (whitespace-normalised) in a tool result; else the result line naming the object."""
    items = []
    for quote in fault.get("evidence") or []:
        q = _norm(str(quote))
        if len(q) < 8:
            continue
        for c in calls:
            if q in _norm(c["full"]):
                items.append({"tool_call_id": c["id"], "excerpt": str(quote)[:300]})
                break
    if not items:
        for c in calls:
            line = next((ln for ln in c["full"].splitlines() if fault["name"] in ln
                         and (not fault["namespace"] or fault["namespace"] in ln or c["tool"] == "get_status")), None)
            if line:
                items.append({"tool_call_id": c["id"], "excerpt": line[:300]})
                break
    return items


def _findings(report, calls, cluster):
    findings, ungrounded = [], []
    seen = "\n".join(c["full"] for c in calls)
    for f in report["faults"]:
        item = {"namespace": f["namespace"], "object": f"{f['kind']}/{f['name']}", "category": f["category"],
                "summary": f.get("summary") or "", "evidence": []}
        if f["category"] == "scaled-to-zero" and cluster.keda_managed(f["namespace"], f["kind"], f["name"]):
            ungrounded.append({**item, "reason": "KEDA manages it: at zero by design (KEDA rule)"})
            continue
        if not f["name"] or f["name"] not in seen or (f["namespace"] and f["namespace"] not in seen):
            ungrounded.append({**item, "reason": "object or namespace appears in no tool result"})
            continue
        item["evidence"] = _evidence(f, calls)
        findings.append(item)
    return findings, ungrounded


def _now():
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id():
    return "r-" + dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


def run(cfg, cluster, namespace=None, thinking=False, run_id=None, log=None):
    """One status run, traced (agent/tracing.py). Returns the API's run object (docs/interface.md)."""
    run_id = run_id or new_run_id()
    with tracing.tracer().start_as_current_span(f"invoke_agent {tracing.SERVICE}") as span:
        span.set_attributes({"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": tracing.SERVICE,
                             "gen_ai.request.model": cfg["model"], "agent.run_id": run_id,
                             "agent.thinking": bool(thinking), "agent.namespace": namespace or "",
                             "agent.prompt_sha256": PROMPT_SHA256})
        out = _run(cfg, cluster, namespace, thinking, run_id, log)
        out["trace_id"] = tracing.trace_id(span)
        span.set_attributes({"agent.status": out["status"], "agent.findings": len(out["findings"]),
                             "agent.ungrounded": len(out["ungrounded"]), "agent.tool_calls": len(out["tool_calls"]),
                             "agent.turns": out["timings"]["turns"]})
        if out["error"]:
            span.set_status(Status(StatusCode.ERROR, out["error"][:200]))
    tracing.flush()
    return out


def _run(cfg, cluster, namespace, thinking, run_id, log):
    started, t0 = _now(), time.monotonic()
    client = OpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"], max_retries=0)
    opts = {"model": cfg["model"], "temperature": 0, "max_tokens": MAX_TOKENS}
    if thinking:
        opts["extra_body"] = {"chat_template_kwargs": {"enable_thinking": True}}
    user = USER_PROMPT
    if namespace:
        user = (f"Report the current status of namespace {namespace}: list every fault there. "
                f"Pass namespace={namespace} to the tools that take one.")
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
    calls, turns, nudged, content, error = [], 0, False, "", None
    model_s = tools_s = 0.0

    def remaining():
        return DEADLINE_S - (time.monotonic() - t0)

    def chat(**kw):
        nonlocal model_s
        if remaining() <= 5:
            raise TimeoutError("deadline exceeded")
        t = time.monotonic()
        with tracing.tracer().start_as_current_span(f"chat {cfg['model']}") as span:
            span.set_attributes({"gen_ai.operation.name": "chat", "gen_ai.request.model": cfg["model"],
                                 "gen_ai.request.temperature": 0, "gen_ai.request.max_tokens": MAX_TOKENS,
                                 "agent.thinking": bool(thinking), "agent.messages": len(msgs),
                                 "agent.request": "final" if "response_format" in kw else "tools"})
            try:
                r = client.with_options(timeout=remaining()).chat.completions.create(messages=msgs, **opts, **kw)
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, type(e).__name__))
                raise
            finally:
                model_s += time.monotonic() - t
            u = r.usage
            span.set_attributes({"gen_ai.response.model": r.model or "",
                                 "gen_ai.response.finish_reasons": [c.finish_reason or "" for c in r.choices],
                                 "gen_ai.usage.input_tokens": u.prompt_tokens if u else 0,
                                 "gen_ai.usage.output_tokens": u.completion_tokens if u else 0,
                                 "agent.tool_calls_requested": len(r.choices[0].message.tool_calls or [])})
            return r

    report = None
    try:
        for _ in range(MAX_TURNS):
            if len([x for x in calls if not x["error"]]) >= MAX_TOOL_CALLS:
                content = ""          # cap reached: no more tools, straight to the final request
                break
            turns += 1
            m = chat(tools=tools.openai_tools()).choices[0].message
            content = m.content or ""
            if not m.tool_calls:
                if not calls and not nudged:
                    nudged = True
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
                if args is not None and namespace and c.function.name in NS_TOOLS and not args.get("namespace"):
                    args["namespace"] = namespace
                if len([x for x in calls if not x["error"]]) >= MAX_TOOL_CALLS:
                    out, err = "error: tool-call limit reached; give your final answer now", True
                elif args is None:
                    out, err = "error: arguments are not JSON", True
                else:
                    t = time.monotonic()
                    with tracing.tracer().start_as_current_span(f"execute_tool {c.function.name}") as span:
                        out = tools.call(cluster, c.function.name, args)
                        err = out.startswith("error:")
                        span.set_attributes({"gen_ai.operation.name": "execute_tool",
                                             "gen_ai.tool.name": c.function.name,
                                             "gen_ai.tool.call.id": f"t{len(calls) + 1}",
                                             "agent.tool.argument_keys": sorted(args),
                                             "agent.tool.result_chars": len(out)})
                        if err:
                            span.set_status(Status(StatusCode.ERROR, out[:120]))
                    tools_s += time.monotonic() - t
                call = {"id": f"t{len(calls) + 1}", "tool": c.function.name, "arguments": args or {},
                        "full": out, "duration_ms": int((time.monotonic() - t) * 1000) if args is not None and not err else 0,
                        "error": err}
                calls.append(call)
                if log:
                    log(call)
                msgs.append({"role": "tool", "tool_call_id": c.id, "content": out})
            content = ""
        report = parse_report(content) if calls else None
        if report is None and calls:
            if content:
                msgs.append({"role": "assistant", "content": content})
            msgs.append({"role": "user", "content": FINAL_ASK})
            r = chat(response_format={"type": "json_schema", "json_schema": {"name": "report", "schema": REPORT_SCHEMA}})
            turns += 1
            report = parse_report(r.choices[0].message.content)
            if report is None:
                error = (f"no valid report (final request: finish_reason={r.choices[0].finish_reason}, "
                         f"content starts {(r.choices[0].message.content or '')[:120]!r})")
        if not calls:
            error = "no tool call"
        elif report is None and not error:
            error = "no valid report"
    except TimeoutError as e:
        error = str(e)
    except Exception as e:      # endpoint or API errors: the run is unknown, not a crash
        error = f"{type(e).__name__}: {e}"[:300]

    findings, ungrounded = _findings(report, calls, cluster) if report else ([], [])
    if report is None:
        status = "unknown"
    elif findings:
        status = "fault"
    elif any("KEDA rule" not in u["reason"] for u in ungrounded):
        status = "unknown"      # the model named objects the tools never showed
    else:
        status = "healthy"
    return {
        "run_id": run_id, "status": status, "demo": False, "namespace": namespace,
        "findings": findings, "ungrounded": ungrounded, "summary": (report or {}).get("summary", ""),
        "tool_calls": [{"id": c["id"], "tool": c["tool"], "arguments": c["arguments"], "result": c["full"][:RESULT_KEEP],
                        "result_chars": len(c["full"]), "truncated": len(c["full"]) > RESULT_KEEP,
                        "duration_ms": c["duration_ms"], "error": c["error"]} for c in calls],
        "model": {"name": cfg["model"], "base_url": cfg["base_url"], "temperature": 0, "max_tokens": MAX_TOKENS,
                  "thinking": bool(thinking), "max_tool_calls": MAX_TOOL_CALLS, "max_turns": MAX_TURNS,
                  "prompt_sha256": PROMPT_SHA256},
        "timings": {"started": started, "finished": _now(), "total_s": round(time.monotonic() - t0, 1),
                    "model_s": round(model_s, 1), "tools_s": round(tools_s, 2), "turns": turns},
        "error": error,
    }
