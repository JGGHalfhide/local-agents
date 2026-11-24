#!/usr/bin/env python3
"""Score status-reporter runs against the injected cases (docs/eval-status.md).

  score.py <results-dir>        (written by eval/status/run_eval.py)

Reads eval/status/cases.yaml and <results-dir>/<case>.json (the API's run
object, docs/interface.md) and writes <results-dir>/scores.md and
scores.json. Per case, every check must hold to pass:

  fault case:   detect (status fault), locate (a finding in agent-eval-<id>
                on an accepted object), classify (its category is the
                expected one or an accepted alternative)
  control:      no finding in agent-eval-<id>
  all cases:    no finding in another agent-eval-* namespace; grounding (no
                finding dropped for naming objects the tools never showed);
                tool validity (no invalid tool call, at most 8 executed)

Findings in platform namespaces are listed as "ambient" and not scored
(the cluster is healthy apart from the case; an ambient fault is reported,
not counted against the case).
"""
import fnmatch
import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
MAX_TOOL_CALLS = 8


def score_case(cid, case, run):
    ns = f"agent-eval-{cid}"
    findings = run.get("findings") or []
    here = [f for f in findings if f["namespace"] == ns]
    other_eval = [f for f in findings if f["namespace"].startswith("agent-eval-") and f["namespace"] != ns]
    ambient = [f for f in findings if not f["namespace"].startswith("agent-eval-")]
    calls = run.get("tool_calls") or []
    invalid = [c for c in calls if c["error"] and not c["result"].startswith("error: tool-call limit")]
    executed = [c for c in calls if not c["error"]]
    ungrounded = [u for u in run.get("ungrounded") or [] if "KEDA rule" not in u.get("reason", "")]
    checks = {}
    if case["kind"] == "fault":
        accepted = case["objects"]
        cats = {case["category"], *case.get("also_accept", [])}
        located = [f for f in here if any(fnmatch.fnmatch(f["object"], pat) for pat in accepted)]
        checks["detect"] = run.get("status") == "fault"
        checks["locate"] = bool(located)
        checks["classify"] = any(f["category"] in cats for f in located)
    else:
        checks["no_fault_here"] = not here
    checks["no_false_positive"] = not other_eval
    checks["grounding"] = not ungrounded
    checks["tool_validity"] = not invalid and len(executed) <= MAX_TOOL_CALLS
    return {"case": cid, "kind": case["kind"], "pass": all(checks.values()), "checks": checks,
            "status": run.get("status"), "error": run.get("error"),
            "found_here": [f"{f['category']} {f['object']}" for f in here],
            "ambient": [f"{f['category']} {f['namespace']}/{f['object']}" for f in ambient],
            "tool_calls": len(executed), "seconds": (run.get("timings") or {}).get("total_s"),
            "run_id": run.get("run_id")}


def main():
    out = pathlib.Path(sys.argv[1])
    cases = yaml.safe_load((ROOT / "eval/status/cases.yaml").read_text())["cases"]
    rows = []
    for cid, case in cases.items():
        f = out / f"{cid}.json"
        if f.exists():
            rows.append(score_case(cid, case, json.loads(f.read_text())))
    (out / "scores.json").write_text(json.dumps(rows, indent=1) + "\n")
    faults = [r for r in rows if r["kind"] == "fault"]
    controls = [r for r in rows if r["kind"] == "control"]
    lines = [f"Faults passed: {sum(r['pass'] for r in faults)}/{len(faults)}; "
             f"controls passed: {sum(r['pass'] for r in controls)}/{len(controls)}.", "",
             "| Case | Kind | Pass | Failed checks | Reported in the case namespace | Ambient findings | Tool calls | Seconds |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        failed = ", ".join(k for k, v in r["checks"].items() if not v) or "-"
        lines.append(f"| {r['case']} | {r['kind']} | {'yes' if r['pass'] else 'NO'} | {failed} | "
                     f"{'; '.join(r['found_here']) or '-'} | {'; '.join(r['ambient']) or '-'} | "
                     f"{r['tool_calls']} | {r['seconds']} |")
    (out / "scores.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
