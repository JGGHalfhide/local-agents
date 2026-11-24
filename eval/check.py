#!/usr/bin/env python3
"""Check the evaluation cases, and score answers against them.

  check.py                      validate eval/cases/*.yaml: schema, unique ids,
                                patterns compile, no scoring term in the input
  check.py score answers.json   automatic first pass of docs/eval.md's scoring

answers.json: {"c01": {"cause": "...", "fix": "..."}, ...}
Prints one line per case and writes nothing; the human review in
docs/eval.md turns this first pass into final scores.
"""
import json
import pathlib
import re
import sys

import yaml

CASES = pathlib.Path(__file__).resolve().parent / "cases"
REQUIRED = {"id", "title", "category", "difficulty", "source", "provenance",
            "verbatim", "input", "expected"}
EXPECTED = {"cause", "fix", "cause_terms", "fix_terms", "harmful"}
PROVENANCE = {"reconstructed", "captured"}
DIFFICULTY = {"easy", "medium", "hard"}


def load():
    cases = []
    for p in sorted(CASES.glob("c*.yaml")):
        c = yaml.safe_load(p.read_text())
        c["_file"] = p.name
        cases.append(c)
    return cases


def groups_match(groups, text):
    """Every group must match; a group matches if any of its patterns does."""
    return all(any(re.search(p, text, re.I | re.S) for p in g) for g in groups)


def validate(cases):
    errors = []
    ids = set()
    for c in cases:
        f = c["_file"]
        missing = REQUIRED - c.keys()
        if missing:
            errors.append(f"{f}: missing {sorted(missing)}")
            continue
        e = c["expected"]
        if EXPECTED - e.keys():
            errors.append(f"{f}: expected missing {sorted(EXPECTED - e.keys())}")
            continue
        if c["id"] in ids:
            errors.append(f"{f}: duplicate id {c['id']}")
        ids.add(c["id"])
        if not f.startswith(c["id"] + "-"):
            errors.append(f"{f}: file name does not start with id {c['id']}")
        if c["provenance"] not in PROVENANCE:
            errors.append(f"{f}: provenance must be one of {sorted(PROVENANCE)}")
        if c["difficulty"] not in DIFFICULTY:
            errors.append(f"{f}: difficulty must be one of {sorted(DIFFICULTY)}")
        for key in ("cause_terms", "fix_terms"):
            if not e[key] or not all(isinstance(g, list) and g for g in e[key]):
                errors.append(f"{f}: {key} must be a non-empty list of non-empty lists")
        pats = [p for k in ("cause_terms", "fix_terms") for g in e[k] for p in g] + e["harmful"]
        for p in pats:
            try:
                re.compile(p)
            except re.error as ex:
                errors.append(f"{f}: bad pattern {p!r}: {ex}")
        if errors and errors[-1].startswith(f + ": bad pattern"):
            continue
        # Leak check: a term group that the input already satisfies would
        # reward an answer that just repeats the input.
        for key in ("cause_terms", "fix_terms"):
            if key in (c.get("leak_ok") or {}):
                print(f"{f}: {key} leak allowed: {c['leak_ok'][key]}")
                continue
            if groups_match(e[key], c["input"]):
                hits = [p for g in e[key] for p in g if re.search(p, c["input"], re.I | re.S)]
                errors.append(f"{f}: {key} is satisfied by the input alone (via {hits})")
        # The expected answer must pass its own terms, and not be harmful.
        if not groups_match(e["cause_terms"], e["cause"]):
            errors.append(f"{f}: expected cause does not match cause_terms")
        if not groups_match(e["fix_terms"], e["fix"]):
            errors.append(f"{f}: expected fix does not match fix_terms")
        for p in e["harmful"]:
            if re.search(p, e["fix"], re.I | re.S):
                errors.append(f"{f}: expected fix matches harmful pattern {p!r}")
    return errors


def score(cases, answers):
    print(f"{'id':<5}{'cause':>6}{'fix':>5}  harmful  title")
    tot_c = tot_f = n_h = 0
    for c in cases:
        a = answers.get(c["id"])
        if a is None:
            print(f"{c['id']:<5}{'-':>6}{'-':>5}  -        (no answer) {c['title']}")
            continue
        e = c["expected"]
        cause_ok = groups_match(e["cause_terms"], a.get("cause", ""))
        fix_ok = groups_match(e["fix_terms"], a.get("fix", ""))
        harm = [p for p in e["harmful"] if re.search(p, a.get("fix", ""), re.I | re.S)]
        tot_c += cause_ok
        tot_f += fix_ok
        n_h += bool(harm)
        print(f"{c['id']:<5}{'match' if cause_ok else 'no':>6}{'match' if fix_ok else 'no':>5}"
              f"  {'YES' if harm else 'no':<8} {c['title']}")
    n = len(cases)
    print(f"cause terms matched {tot_c}/{n}, fix terms matched {tot_f}/{n}, harmful flagged {n_h}")


def main():
    cases = load()
    if len(sys.argv) == 1:
        errors = validate(cases)
        for e in errors:
            print(e)
        print(f"{len(cases)} cases, {len(errors)} problems")
        sys.exit(1 if errors else 0)
    if sys.argv[1] == "score" and len(sys.argv) == 3:
        score(cases, json.loads(pathlib.Path(sys.argv[2]).read_text()))
        return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
