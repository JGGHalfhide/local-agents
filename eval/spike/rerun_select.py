#!/usr/bin/env python3
"""Pick the spike runs to redo after the completion cap went from 512 to
1024 tokens (11/24), and merge the redone runs back (stdlib only).

  rerun_select.py select <run-dir>              prints candidate:fixture pairs
  rerun_select.py merge <run-dir> <rerun-dir> <out-dir>

select: runs made at the old cap (their requests carry max_tokens or
max_completion_tokens 512) that failed, or in which any response stopped at
the cap (finish_reason "length"). A run that passed at 512 without reaching
the cap is kept: with greedy decoding the cap never bound it, so 1024 would
give the same output.

merge: <run-dir>'s runs and proxy records, minus the redone run ids, plus
everything in <rerun-dir>; meta.json from <run-dir> with the rerun noted.
"""
import collections
import json
import pathlib
import sys


def load(d):
    d = pathlib.Path(d)
    runs = [json.loads(l) for l in (d / "runs.jsonl").read_text().splitlines()]
    proxy = [json.loads(l) for l in (d / "proxy.jsonl").read_text().splitlines()]
    return runs, proxy


def select(d):
    runs, proxy = load(d)
    by_run = collections.defaultdict(list)
    for r in proxy:
        by_run[r["run"]].append(r)
    out = []
    for r in runs:
        recs = by_run[r["run"]]
        caps = {(x["request"] or {}).get("max_tokens") or (x["request"] or {}).get("max_completion_tokens") for x in recs}
        if 512 not in caps:
            continue
        res = r["result"] or {}
        failed = r["exit"] != 0 or bool(res.get("exception")) or not res.get("report")
        hit_cap = any(ch.get("finish_reason") == "length"
                      for x in recs for ch in (x["response"] or {}).get("choices") or [])
        if failed or hit_cap:
            out.append(f"{r['candidate']}:{r['fixture']}")
    return out


def merge(d, rd, od):
    runs, proxy = load(d)
    rruns, rproxy = load(rd)
    redone = {r["run"] for r in rruns}
    od = pathlib.Path(od)
    od.mkdir(parents=True, exist_ok=True)
    (od / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in runs if r["run"] not in redone)
                                   + "".join(json.dumps(r) + "\n" for r in rruns))
    (od / "proxy.jsonl").write_text("".join(json.dumps(r) + "\n" for r in proxy if r["run"] not in redone)
                                    + "".join(json.dumps(r) + "\n" for r in rproxy))
    meta = json.loads((pathlib.Path(d) / "meta.json").read_text())
    meta["rerun_at_1024"] = sorted(redone)
    meta["caps"]["max_tokens"] = "1024 (512 for kept runs that never reached it)"
    (od / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"merged: {len(runs) - len(redone & {r['run'] for r in runs})} kept + {len(rruns)} redone")


if __name__ == "__main__":
    if sys.argv[1] == "select":
        print(",".join(select(sys.argv[2])))
    else:
        merge(sys.argv[2], sys.argv[3], sys.argv[4])
