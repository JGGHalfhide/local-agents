#!/usr/bin/env python3
"""Score an ADR 0002 spike run (stdlib only).

  score.py <out-dir>      (the directory run_spike.py wrote)

Reads runs.jsonl (what each adapter returned) and proxy.jsonl (every
request and response the model saw and emitted), and prints a markdown
summary per candidate:

- success: the run ended without an exception, with a schema-valid report,
  no invalid tool call, and no more than MAX_TOOL_CALLS executed calls;
- tool calls emitted by the model (from the proxy log, so the same check
  for every runtime): unknown name, arguments that are not JSON or fail
  the tool's schema. Each framework's own final-output tool
  (pydantic-ai final_result, smolagents final_answer) counts as valid;
- requests, prompt and completion tokens, wall time per run;
- correctness (informational; prompt and tools are shared, so this is
  the model, not the runtime): fault fixtures, the expected fault found in
  its namespace with its category; every fixture, faults reported in
  agent-eval-* namespaces that were not injected, and reported faults in
  total;
- repeatability: whether the 3 greedy runs of a candidate x fixture
  emitted the same tool-call sequence and the same report.
"""
import collections
import json
import pathlib
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import common  # noqa: E402

FINAL_TOOLS = {"pydantic-ai": {"final_result"}, "smolagents": {"final_answer"}}
out = pathlib.Path(sys.argv[1])
runs = [json.loads(l) for l in (out / "runs.jsonl").read_text().splitlines()]
proxy = collections.defaultdict(list)
for l in (out / "proxy.jsonl").read_text().splitlines():
    r = json.loads(l)
    if r["path"].endswith("/chat/completions"):
        proxy[r["run"]].append(r)
fixtures = {f: json.loads((pathlib.Path(__file__).parent / "fixtures" / f"{f}.json").read_text())["expected"]
            for f in {r["fixture"] for r in runs}}


def emitted_calls(run_id, cand):
    calls, bad = [], []
    for r in proxy[run_id]:
        for ch in (r["response"] or {}).get("choices") or []:
            for c in (ch.get("message") or {}).get("tool_calls") or []:
                name, raw = c["function"]["name"], c["function"].get("arguments") or "{}"
                calls.append((name, raw))
                if name in FINAL_TOOLS.get(cand, set()):
                    continue
                if name not in common.TOOL_NAMES:
                    bad.append(f"unknown tool {name}")
                    continue
                try:
                    args = json.loads(raw)
                except ValueError:
                    bad.append(f"{name}: arguments not JSON")
                    continue
                errs = common.validate(args if isinstance(args, dict) else None, common.tool_schema(name))
                if errs:
                    bad.append(f"{name}: {'; '.join(errs)}")
    return calls, bad


def correctness(fixture, report):
    exp = fixtures[fixture]["faults"]
    faults = (report or {}).get("faults") or []
    found = all(any(f["namespace"] == e["namespace"] and f["category"] == e["category"] for f in faults) for e in exp)
    exp_ns = {e["namespace"] for e in exp}
    fp_eval = [f for f in faults if f["namespace"].startswith("agent-eval-") and f["namespace"] not in exp_ns]
    return found if exp else None, len(fp_eval), len(faults)


rows = collections.defaultdict(list)
for r in runs:
    res = r["result"] or {}
    calls, bad = emitted_calls(r["run"], r["candidate"])
    reqs = proxy[r["run"]]
    usage = [(x["response"] or {}).get("usage") or {} for x in reqs]
    found, fp_eval, nfaults = correctness(r["fixture"], res.get("report"))
    executed = len(res.get("calls") or [])
    rows[r["candidate"]].append({
        "fixture": r["fixture"], "i": r["i"],
        "success": r["exit"] == 0 and not res.get("exception") and bool(res.get("report")) and not bad
                   and executed <= common.MAX_TOOL_CALLS,
        "exception": res.get("exception"), "report": res.get("report"), "bad": bad,
        "emitted": len(calls), "executed": executed, "requests": len(reqs),
        "http_errors": sum(x["status"] != 200 for x in reqs),
        "prompt": sum(u.get("prompt_tokens") or 0 for u in usage),
        "completion": sum(u.get("completion_tokens") or 0 for u in usage),
        "seconds": r["wall_seconds"], "found": found, "fp_eval": fp_eval, "nfaults": nfaults,
        "seq": [c[0] for c in calls],
    })

print("| Candidate | Runs | Success | Invalid tool calls | Exceptions | Tool calls emitted / executed (mean) | Requests (mean) | Prompt tokens (mean) | Completion tokens (mean) | Wall s (median) | Expected fault found | False faults in agent-eval-* | Faults reported (mean) |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for c in ["plain-stdlib", "plain-openai", "pydantic-ai", "langgraph", "smolagents"]:
    rs = rows.get(c)
    if not rs:
        continue
    fault_runs = [x for x in rs if x["found"] is not None]
    print(f"| {c} | {len(rs)} | {sum(x['success'] for x in rs)}/{len(rs)} | {sum(len(x['bad']) for x in rs)} | "
          f"{sum(bool(x['exception']) for x in rs)} | {statistics.mean(x['emitted'] for x in rs):.1f} / {statistics.mean(x['executed'] for x in rs):.1f} | "
          f"{statistics.mean(x['requests'] for x in rs):.1f} | {statistics.mean(x['prompt'] for x in rs):.0f} | "
          f"{statistics.mean(x['completion'] for x in rs):.0f} | {statistics.median(x['seconds'] for x in rs):.0f} | "
          f"{sum(bool(x['found']) for x in fault_runs)}/{len(fault_runs)} | {sum(x['fp_eval'] for x in rs)} | "
          f"{statistics.mean(x['nfaults'] for x in rs):.1f} |")

print("\n## Per fixture: successes / runs, and repeatability of the 3 greedy runs\n")
fx_names = sorted({x["fixture"] for rs in rows.values() for x in rs})
print("| Candidate | " + " | ".join(fx_names) + " |")
print("|---|" + "---|" * len(fx_names))
for c, rs in rows.items():
    cells = []
    for f in fx_names:
        xs = [x for x in rs if x["fixture"] == f]
        same_seq = len({tuple(x["seq"]) for x in xs}) == 1
        same_rep = len({json.dumps(x["report"], sort_keys=True) for x in xs}) == 1
        cells.append(f"{sum(x['success'] for x in xs)}/{len(xs)}, "
                     f"{'same calls' if same_seq else 'calls differ'}, {'same report' if same_rep else 'report differs'}")
    print(f"| {c} | " + " | ".join(cells) + " |")

print("\n## Failures\n")
for c, rs in rows.items():
    for x in rs:
        if not x["success"]:
            why = x["exception"] or ("; ".join(x["bad"]) if x["bad"] else
                                     ("no report" if not x["report"] else f"{x['executed']} calls"))
            print(f"- {c} / {x['fixture']} / {x['i']}: {why[:300]}")
