"""Shared parts of the ADR 0002 runtime spike (stdlib only, imported by every
candidate's adapter): config, the status reporter's tools served from a
fixture, the system prompt, the report schema, and a minimal JSON-schema
check. Spec: docs/eval-status.md (tools, caps); method: docs/adr/0002.

Every candidate gets the same tools, prompt, schema and caps, so the spike
compares runtimes, not prompts. Tool results are compact text rows, capped
at MAX_RESULT_CHARS (~1,000 tokens, docs/eval-status.md).
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
MAX_RESULT_CHARS = 3500      # ~1,000 tokens
MAX_TOOL_CALLS = 8
MAX_TOKENS = 1024            # completion per turn, thinking off (512 cut final reports: spike 11/24)
MAX_TURNS = MAX_TOOL_CALLS + 2   # model requests in the tool loop; then one final request without tools
FINAL_ASK = "Give the final report as JSON only."

CATEGORIES = ["scaled-to-zero", "image-pull", "crash-loop", "oom-killed",
              "admission-denied", "unschedulable", "storage-unbound",
              "gitops-unhealthy", "node-not-ready", "other"]

SYSTEM_PROMPT = f"""You are a read-only Kubernetes platform status reporter.
Use the tools to look at the cluster, then report every fault you find.
A fault is something broken now: a workload that should run but cannot,
pods crash-looping, OOM-killed, failing to pull, rejected at admission,
unschedulable, an unbound volume. These are NOT faults: a workload scaled to
zero by KEDA or another autoscaler, a Job that completed, old warning events
for objects that are healthy now.
Rules: call at most {MAX_TOOL_CALLS} tools. Only name namespaces and objects
that appear in tool output. Each fault gets one category from:
{", ".join(CATEGORIES)}.
Your final answer is a JSON object only:
{{"faults": [{{"namespace": "...", "kind": "...", "name": "...", "category": "...",
"evidence": ["..."]}}], "summary": "..."}}
An empty "faults" list means no fault."""

USER_PROMPT = "Report the current status of the cluster: list every fault."

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "faults": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "namespace": {"type": "string"},
                "kind": {"type": "string"},
                "name": {"type": "string"},
                "category": {"type": "string", "enum": CATEGORIES},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["namespace", "kind", "name", "category", "evidence"],
            "additionalProperties": False}},
        "summary": {"type": "string"},
    },
    "required": ["faults", "summary"],
    "additionalProperties": False,
}

_NS = {"namespace": {"type": "string", "description": "Namespace; omit for all namespaces"}}
TOOLS = [
    ("list_namespaces", "List namespaces and their phase.", {}, []),
    ("list_pods", "List pods: phase, ready, restarts, waiting reason, last termination. Not-ready pods first.", _NS, []),
    ("list_workloads", "List Deployments, StatefulSets, DaemonSets, ReplicaSets and Jobs: desired/ready/available and conditions that are not True.", _NS, []),
    ("list_events", "List Warning events, newest first, deduplicated by object and reason.", _NS, []),
    ("list_keda_objects", "List KEDA ScaledObjects and HTTPScaledObjects: target, min/max replicas, Ready, Active, Paused.", _NS, []),
    ("get_status", "Status and conditions of one object.",
     {"kind": {"type": "string", "enum": ["Pod", "Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "ScaledObject"]},
      "namespace": {"type": "string"}, "name": {"type": "string"}},
     ["kind", "namespace", "name"]),
]
TOOL_NAMES = [t[0] for t in TOOLS]


def tool_schema(name):
    for n, _desc, props, req in TOOLS:
        if n == name:
            return {"type": "object", "properties": props, "required": req, "additionalProperties": False}
    return None


def openai_tools():
    """Tool definitions in the OpenAI chat-completions format."""
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": tool_schema(n)}}
            for n, d, _p, _r in TOOLS]


def validate(value, schema, path="$"):
    """Minimal JSON-schema check for the shapes used here; returns a list of errors."""
    errs = []
    t = schema.get("type")
    types = {"object": dict, "array": list, "string": str}
    if t in types and not isinstance(value, types[t]):
        return [f"{path}: expected {t}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not in enum")
    if t == "object":
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in value:
                errs.append(f"{path}.{k}: missing")
        for k, v in value.items():
            if k in props:
                errs += validate(v, props[k], f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}.{k}: not allowed")
    if t == "array":
        for i, v in enumerate(value):
            errs += validate(v, schema.get("items", {}), f"{path}[{i}]")
    return errs


def load_config(path):
    """Backend-neutral client config: base_url, model, api_key_env (name of an
    env var holding the key; empty = no key, as for the lab endpoint)."""
    import os
    c = json.loads(pathlib.Path(path).read_text())
    key = os.environ.get(c["api_key_env"], "") if c.get("api_key_env") else ""
    return c["base_url"], c["model"], key or "none"


def load_report(text):
    """Parse a final answer into the report; returns (report or None, errors)."""
    if isinstance(text, dict):
        obj = text
    else:
        s = str(text).strip()
        if s.startswith("```"):
            s = s.strip("`")
            s = s[s.find("{"):] if "{" in s else s
        i, j = s.find("{"), s.rfind("}")
        if i < 0 or j < i:
            return None, ["no JSON object"]
        try:
            obj = json.loads(s[i:j + 1])
        except json.JSONDecodeError as e:
            return None, [f"JSON: {e}"]
    errs = validate(obj, REPORT_SCHEMA)
    return (obj if not errs else None), errs


class Fixture:
    """Serves tool results from a fixture file (rows already summarised)."""

    def __init__(self, path):
        self.data = json.loads(pathlib.Path(path).read_text())
        self.calls = []

    def _rows(self, key, namespace=None):
        rows = self.data[key]
        if namespace:
            rows = [r for r in rows if r.get("namespace") == namespace]
        return rows

    @staticmethod
    def _render(header, rows, cols):
        lines = ["\t".join(cols)] + ["\t".join(str(r.get(c, "")) for c in cols) for r in rows]
        out, n = [], 0
        for line in lines:
            if n + len(line) + 1 > MAX_RESULT_CHARS - 80:
                out.append(f"... {len(lines) - len(out)} more rows omitted; narrow by namespace")
                break
            out.append(line)
            n += len(line) + 1
        return header + "\n" + "\n".join(out)

    def call(self, name, args):
        self.calls.append({"name": name, "args": args})
        errs = validate(args or {}, tool_schema(name) or {"type": "object"}) if name in TOOL_NAMES else ["unknown tool"]
        if errs:
            return "error: " + "; ".join(errs)
        ns = (args or {}).get("namespace") or None
        if name == "list_namespaces":
            return self._render("namespaces", self._rows("namespaces"), ["name", "phase"])
        if name == "list_pods":
            rows = sorted(self._rows("pods", ns), key=lambda r: (r["ok"], r["namespace"], r["name"]))
            return self._render("pods", rows, ["namespace", "name", "phase", "ready", "restarts", "waiting", "last_terminated", "owner"])
        if name == "list_workloads":
            return self._render("workloads", self._rows("workloads", ns),
                                ["namespace", "kind", "name", "desired", "ready", "available", "conditions"])
        if name == "list_events":
            return self._render("warning events", self._rows("events", ns),
                                ["namespace", "object", "reason", "count", "age", "message"])
        if name == "list_keda_objects":
            return self._render("keda objects", self._rows("keda", ns),
                                ["namespace", "kind", "name", "target", "min", "max", "ready", "active", "paused"])
        if name == "get_status":
            key = f"{args['kind']}/{args['namespace']}/{args['name']}"
            st = self.data["status"].get(key)
            return json.dumps(st)[:MAX_RESULT_CHARS] if st else f"not found: {key}"
        return "error: unknown tool"


def parse_args(raw):
    """Tool-call arguments as a dict, or None if they are not a JSON object."""
    try:
        args = json.loads(raw or "{}")
    except ValueError:
        return None
    return args if isinstance(args, dict) else None


def sanitized(raw):
    """Arguments safe to resend in the history: llama-server re-parses every
    earlier tool call when it builds the prompt and answers 500 for the whole
    conversation if one is not JSON (spike round 1, 11/24)."""
    return raw if parse_args(raw) is not None else "{}"


def result_line(**kw):
    """One JSON line on stdout: what the orchestrator records for the run."""
    print("RESULT " + json.dumps(kw, default=str), flush=True)
