#!/usr/bin/env python3
"""Automatic first pass for a run, and the human review sheet (docs/eval.md).

  review_sheet.py results/<run>

For every configuration directory in the run (with raw.jsonl), writes
<run>/scores.yaml: per case the proposed cause/fix score (2 if the case's
terms match, else 0), harmful flags, whether the case must be reviewed, and
latency/tokens; plus <run>/summary.md, the per-configuration table.

Review rule (accepted 11/23): every proposed 0, every harmful flag, and one
in four of the proposed 2s, chosen by case id (ids whose number is 1 mod 4:
c01, c05, c09, ...). The reviewer edits `cause`/`fix`/`harmful` in
scores.yaml and sets `reviewed: true` with a `note`; rerunning this script
keeps reviewed entries.
"""
import json
import pathlib
import re
import statistics
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from check import groups_match, load  # noqa: E402


def sampled(case_id):
    return int(case_id[1:]) % 4 == 1


def pct(values, p):
    if not values:
        return None
    v = sorted(values)
    k = max(0, min(len(v) - 1, round(p / 100 * (len(v) - 1))))
    return v[k]


def main():
    run = pathlib.Path(sys.argv[1])
    cases = {c["id"]: c for c in load()}
    path = run / "scores.yaml"
    old = yaml.safe_load(path.read_text()) if path.exists() else {}
    sheet = {}
    rows = []
    for d in sorted(p for p in run.iterdir() if (p / "raw.jsonl").exists()):
        cfg = d.name
        entries = {}
        lat, toks, think = [], [], []
        for line in (d / "raw.jsonl").read_text().splitlines():
            r = json.loads(line)
            c = cases[r["id"]]
            e = c["expected"]
            a = r.get("answer") or {}
            cause, fix = str(a.get("cause", "")), str(a.get("fix", ""))
            harm = [p for p in e["harmful"] if re.search(p, fix, re.I | re.S)]
            pc = 2 if groups_match(e["cause_terms"], cause) else 0
            pf = 2 if groups_match(e["fix_terms"], fix) else 0
            entry = {
                "proposed": {"cause": pc, "fix": pf, "harmful": bool(harm)},
                "harmful_patterns": harm,
                "review": pc == 0 or pf == 0 or bool(harm) or sampled(r["id"]),
                "cause": pc, "fix": pf, "harmful": bool(harm),
                "reviewed": False, "note": "",
                "error": r.get("error") or r.get("parse_error"),
                "seconds": r.get("seconds"),
                "completion_tokens": r.get("completion_tokens"),
                "finish_reason": r.get("finish_reason"),
            }
            prev = (old.get(cfg) or {}).get(r["id"])
            if prev and prev.get("reviewed"):
                for k in ("cause", "fix", "harmful", "reviewed", "note"):
                    entry[k] = prev[k]
            entries[r["id"]] = entry
            if r.get("seconds") is not None:
                lat.append(r["seconds"])
                toks.append(r["completion_tokens"])
                think.append(r.get("reasoning_chars") or 0)
        sheet[cfg] = dict(sorted(entries.items()))
        n = len(entries)
        es = entries.values()
        rows.append({
            "config": cfg, "n": n,
            "cause2": sum(x["cause"] == 2 for x in es),
            "fix2": sum(x["fix"] == 2 for x in es),
            "both": sum(x["cause"] == 2 and x["fix"] == 2 for x in es),
            "points": sum(x["cause"] + x["fix"] for x in es),
            "harmful": sum(bool(x["harmful"]) for x in es),
            "nofault_ok": sum(x["cause"] == 2 and x["fix"] == 2 for k, x in entries.items()
                              if cases[k].get("no_fault")),
            "reviewed": sum(x["reviewed"] for x in es),
            "to_review": sum(x["review"] for x in es),
            "errors": sum(bool(x["error"]) for x in es),
            "p50": pct(lat, 50), "p95": pct(lat, 95),
            "tok": round(statistics.mean(toks)) if toks else None,
            "length": sum(x["finish_reason"] == "length" for x in es),
        })
    path.write_text(yaml.safe_dump(sheet, sort_keys=False, width=100))
    nf = sum(1 for c in cases.values() if c.get("no_fault"))
    lines = [
        "| Config | Cause = 2 | Fix = 2 | Both | Points (of 4n) | Harmful | No-fault right | Latency p50 / p95 (s) | Completion tokens (mean) | Cut at max_tokens | Errors | Reviewed |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['config']} | {r['cause2']}/{r['n']} | {r['fix2']}/{r['n']} | {r['both']}/{r['n']} | "
            f"{r['points']}/{4 * r['n']} | {r['harmful']} | {r['nofault_ok']}/{nf} | {r['p50']} / {r['p95']} | "
            f"{r['tok']} | {r['length']} | {r['errors']} | {r['reviewed']}/{r['to_review']} |")
    status = "final (reviewed)" if all(r["reviewed"] == r["to_review"] for r in rows) else \
        "automatic first pass only; human review pending"
    (run / "summary.md").write_text(f"Scores: {status}.\n\n" + "\n".join(lines) + "\n")
    print((run / "summary.md").read_text())


if __name__ == "__main__":
    main()
