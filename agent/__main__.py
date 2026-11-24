"""Entry point: python -m agent [--version] [--tools-only] [--config FILE]

Prints one status report as JSON on stdout (trace on stderr). Config is
backend-neutral (ADR 0002): a JSON file with base_url, model and
api_key_env (the name of an environment variable; empty for the lab
endpoint, which needs no key: ADR 0001). Defaults: AGENT_CONFIG or
/opt/agent/config.json, else the in-cluster endpoint.
Cluster source: agent/k8s.py (in-cluster, KUBE_API, or KUBE_RECORDED).
--tools-only runs every tool once and prints the outputs (no model call).
"""
import argparse
import json
import os
import pathlib
import sys

from agent import __version__

DEFAULT = {"base_url": "http://llm-api.llm.svc:8080/v1", "model": "qwen3.5-4b", "api_key_env": ""}


def load_config(path):
    p = pathlib.Path(path or os.environ.get("AGENT_CONFIG") or "/opt/agent/config.json")
    cfg = dict(DEFAULT, **(json.loads(p.read_text()) if p.exists() else {}))
    cfg["api_key"] = (os.environ.get(cfg["api_key_env"], "") if cfg.get("api_key_env") else "") or "none"
    return cfg


def main():
    ap = argparse.ArgumentParser(prog="agent")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--tools-only", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    if a.version:
        import openai
        print(f"local-agents {__version__}, openai {openai.__version__}, python {sys.version.split()[0]}")
        return 0
    from agent import k8s, tools
    cluster = tools.Cluster(k8s.source())
    if a.tools_only:
        for name in tools.NAMES:
            if name != "get_status":
                print(f"===== {name}\n{tools.call(cluster, name, {})}\n")
        return 0
    from agent import loop

    def log(name, args, out):
        print(f"tool {name} {json.dumps(args)} -> {len(out)} chars", file=sys.stderr)

    report, trace = loop.run(load_config(a.config), cluster, log)
    print(json.dumps(trace), file=sys.stderr)
    print(json.dumps(report, indent=1))
    return 0 if report is not None else 1


if __name__ == "__main__":
    sys.exit(main())
