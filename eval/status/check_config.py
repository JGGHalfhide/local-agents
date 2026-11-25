#!/usr/bin/env python3
"""A prompt change is a commit, and the eval reruns on it (ROADMAP Week 4).

Fails unless some results/*-status-eval/ directory holds a run for every
case in run_eval.CASES recorded with the config_sha256 of the prompts and
limits in deploy/agents/prompts/ now (agent/profile.py). Change a prompt or
a limit, rerun the fault-injection eval (eval/status/run_eval.py) into a new
results directory, and commit both together.

Standard library only (runs in CI with no cluster).
Usage: python3 eval/status/check_config.py
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent import profile  # noqa: E402

CASES = ["f01", "f02", "f04", "f05", "f06", "f07", "f08", "f10", "k1", "k2", "k3", "k4", "k5"]


def main():
    want = profile.config_sha256()
    found = []
    for d in sorted((ROOT / "results").glob("*-status-eval")):
        shas = {}
        for c in CASES:
            f = d / f"{c}.json"
            shas[c] = (json.loads(f.read_text()).get("model") or {}).get("config_sha256") if f.exists() else None
        if all(v == want for v in shas.values()):
            print(f"ok: {d.relative_to(ROOT)} has all {len(CASES)} cases with config_sha256 {want[:12]}")
            return 0
        found.append(f"{d.relative_to(ROOT)}: {sum(v == want for v in shas.values())}/{len(CASES)}")
    print(f"FAIL: no eval results for the current prompts and limits (config_sha256 {want[:12]}, "
          f"deploy/agents/prompts/). Rerun eval/status/run_eval.py into results/<week>-status-eval/ "
          f"and commit it with the change. Seen: {'; '.join(found) or 'none'}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
