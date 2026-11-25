"""The status reporter's prompts and limits, loaded from files (Week 4).

The files live in deploy/agents/prompts/ and reach the pod as a ConfigMap
that Argo CD syncs (kustomize configMapGenerator, hash-suffixed name, so a
change rolls the Deployment): a prompt or limit change is a commit. The
Deployment points AGENT_PROMPTS_DIR at the mount; in a checkout the repo's
directory is the default.

Two hashes go into every run object and trace:
- prompt_sha256: the rendered system prompt (same value as before Week 4,
  3b79b738..., for comparison with older results);
- config_sha256: all FILES below, in order, name and content. The CI check
  (eval/status/check_config.py) requires eval results recorded with the
  current config_sha256: a change here needs an eval rerun to merge.

Standard library only (the CI check imports it without the agent's wheels).
"""
import hashlib
import json
import os
import pathlib

FILES = ["system.txt", "user.txt", "user-namespace.txt", "final-ask.txt", "look-first.txt", "limits.json"]
LIMITS = {"max_tool_calls", "max_tokens", "tool_result_chars"}
REPO_DIR = pathlib.Path(__file__).resolve().parents[1] / "deploy" / "agents" / "prompts"


def directory():
    return pathlib.Path(os.environ.get("AGENT_PROMPTS_DIR") or REPO_DIR)


def config_sha256(d=None):
    d = pathlib.Path(d or directory())
    h = hashlib.sha256()
    for name in FILES:
        h.update(name.encode() + b"\0" + (d / name).read_bytes() + b"\0")
    return h.hexdigest()


def load(d=None, categories=()):
    """Read and check the files; render the system prompt."""
    d = pathlib.Path(d or directory())
    missing = [n for n in FILES if not (d / n).is_file()]
    if missing:
        raise FileNotFoundError(f"prompt files missing in {d}: {', '.join(missing)}")
    text = {n: (d / n).read_text().rstrip("\n") for n in FILES if n.endswith(".txt")}
    limits = json.loads((d / "limits.json").read_text())
    if set(limits) != LIMITS or not all(isinstance(v, int) and v > 0 for v in limits.values()):
        raise ValueError(f"limits.json must set exactly {sorted(LIMITS)} to positive integers")
    for name, need in (("system.txt", ("{max_tool_calls}", "{categories}")), ("user-namespace.txt", ("{namespace}",))):
        if any(t not in text[name] for t in need):
            raise ValueError(f"{name} must contain {', '.join(need)}")
    system = text["system.txt"].replace("{max_tool_calls}", str(limits["max_tool_calls"])).replace(
        "{categories}", ", ".join(categories))
    return {"system": system, "user": text["user.txt"], "user_namespace": text["user-namespace.txt"],
            "final_ask": text["final-ask.txt"], "look_first": text["look-first.txt"], "limits": limits,
            "prompt_sha256": hashlib.sha256(system.encode()).hexdigest(), "config_sha256": config_sha256(d)}
