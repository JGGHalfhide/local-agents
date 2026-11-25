"""Entry point.

  python -m agent serve [--port 8080]       operator API (ADR 0005)
  python -m agent [-n NS] [--thinking]      one run, the run object as JSON on stdout
  python -m agent --tools-only              every tool once, no model call
  python -m agent --version

Config is backend-neutral (ADR 0002): a JSON file with base_url, model and
api_key_env (the name of an environment variable; empty for the lab
endpoint, which needs no key: ADR 0001). Path: --config, AGENT_CONFIG, or
/opt/agent/config.json; else the in-cluster endpoint. Cluster source:
agent/k8s.py (in-cluster, KUBE_API, or KUBE_RECORDED).
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
    ap.add_argument("mode", nargs="?", choices=["serve"], help="serve: run the operator API")
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--tools-only", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("-n", "--namespace")
    ap.add_argument("--thinking", action="store_true")
    a = ap.parse_args()
    if a.version:
        import openai
        print(f"local-agents {__version__}, openai {openai.__version__}, python {sys.version.split()[0]}")
        return 0
    from agent import tracing
    tracing.setup()
    if a.mode == "serve":
        from agent import server
        server.serve(load_config(a.config), port=a.port)
        return 0
    from agent import k8s, tools
    cluster = tools.Cluster(k8s.source())
    if a.tools_only:
        for name in tools.NAMES:
            if name not in ("get_status", "pod_metrics"):
                print(f"===== {name}\n{tools.call(cluster, name, {})}\n")
        return 0
    from agent import loop

    def log(call):
        print(f"{call['id']} {call['tool']} {json.dumps(call['arguments'])} -> {len(call['full'])} chars", file=sys.stderr)

    run = loop.run(load_config(a.config), cluster, namespace=a.namespace, thinking=a.thinking, log=log)
    print(json.dumps(run, indent=1))
    return {"healthy": 0, "fault": 1}.get(run["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
