# local-agents

An AI agent running inside the
[platform-lab](https://github.com/JGGHalfhide/platform-lab) Kubernetes
platform, calling the CPU-only LLM endpoint from
[local-airgap-LLM](https://github.com/JGGHalfhide/local-airgap-LLM), with no
internet: its own read-only identity, tools behind NetworkPolicy and
Kyverno, every model and tool call traced, delivered through the same
signed supply chain, and deployed to an airgapped cluster with egress
blocked.

The agent is a read-only **platform status reporter**
([ADR 0003](docs/adr/0003-first-agent-status-reporter.md)): it reads the
cluster through 11 read-only tools, asks Qwen3.5 4B (llama.cpp, CPU) to find
what is broken, checks every finding against what the tools actually
showed, and returns a structured report. It is scored automatically by
injecting real faults into disposable namespaces. One agent by design: the
three repos together show the whole chain end to end, from bare hardware to
an agent on an airgapped cluster
([ADR 0006](docs/adr/0006-scope-one-agent.md)).

![local-agents overview: read-only tools, a local model with grounded findings, a signed agent image, least-privilege policy and an airgapped deploy, tracing and the operator interface, and the measured results](docs/images/overview.png)

**Status:** v1.0 (11/25). Both clusters rebuilt from fresh clones of the
three repos and evaluated; running on the build cluster and on the
airgapped cluster.

## Results

Fault-injection eval, one status run per case through the operator API,
thinking off ([full results](docs/results.md)):

| Cluster | Faults found, located, classified | Healthy controls clean | False findings | Median run |
|---|---|---|---|---|
| Build (Week 4) | 8/8 | 5/5 | 0 | 49 s |
| Airgapped, egress blocked (Week 5) | 8/8 | 5/5 | 0 | 48 s |
| Airgapped, with prompt injection (Week 6) | 10/10 | 5/5 | 0 | 49 s |
| **v1.0, both clusters rebuilt from fresh clones** | 10/10 each | 5/5 each | 0 | 55 s / 47 s |

- **Prompt injection:** instructions planted in a readiness probe's output
  and in an object's name were never followed (6 runs).
- **Thinking** (the model reasons before answering): same scores at three
  times the run time, so it stays off
  ([ADR 0009](docs/adr/0009-status-reporter-thinking-off.md)).
- **Supply chain:** every image signed and verified at admission on both
  clusters; an unsigned image is rejected; 0 image pull errors on the
  airgapped cluster.
- **Read-only:** no write tools, no write RBAC
  ([ADR 0010](docs/adr/0010-no-write-actions.md)).

Every number has its raw output committed under `results/` or
`docs/scans/`, and failed first passes are kept with their causes.

## What it looks like

`agentctl` on the airgapped cluster: health, a live run, the run list and
the tool-call trace ([recording](docs/media/agentctl.cast),
`asciinema play docs/media/agentctl.cast`):

![agentctl walk-through](docs/media/agentctl.gif)

The read-only web view (no JavaScript, strict CSP; runs start only through
the API):

![web view: recent runs](docs/media/web-runs.png)

![web view: one run with its finding and tool calls](docs/media/web-run.png)

Every run is traced (metadata only, no prompt or tool text): the Grafana
dashboard built from the traces, and one run's model and tool calls in
Tempo:

![Grafana dashboard: runs by status, failures, run duration, thinking](docs/media/grafana-dashboard.png)

![Tempo trace of one run: chat and execute_tool spans](docs/media/tempo-trace.png)

## Architecture

```mermaid
flowchart LR
  subgraph agents["namespace agents"]
    cron["CronJob (hourly)<br/>agentctl"]
    op["operator<br/>agentctl / web view<br/>via port-forward"]
    sr["status-reporter<br/>API v1 + web view<br/>tool loop, 11 read-only tools"]
    prompts[("prompts + limits<br/>ConfigMap (GitOps)")]
  end
  subgraph llm["local-airgap-LLM"]
    icp["KEDA HTTP interceptor"]
    srv["llama-server<br/>Qwen3.5 4B, CPU<br/>scale to zero"]
  end
  api["Kubernetes API<br/>get/list/watch only"]
  tempo["Tempo + Grafana<br/>(platform-lab)"]
  cron -- "POST /v1/status" --> sr
  op -. "port-forward" .-> sr
  prompts --> sr
  sr -- "chat completions + tool calls" --> icp --> srv
  sr -- "GET (read-only ServiceAccount)" --> api
  sr -- "OTLP spans, metadata only" --> tempo
  reg["Zot (build) / Zarf registry (airgap)<br/>signed image, Kyverno verifies"] -. "pull by digest" .-> sr
  argo["Argo CD (build) / Zarf package (airgap)"] -. "deploy/" .-> agents
```

How a run moves through it, and every component with its version and why:
[docs/stack.md](docs/stack.md).

## How it fits

- **platform-lab** provides the clusters: VMs (Terraform), OS hardening,
  RKE2, Argo CD, Zot, Kyverno and cosign, monitoring and Tempo, Velero,
  KEDA, Zarf and the airgap flow.
- **local-airgap-LLM** provides the model endpoint: Qwen3.5 4B on
  llama.cpp, OpenAI-compatible, scale to zero, the model as a signed image.
- **This repo** provides the agent: its image, identity and policies,
  tools, prompts and limits, tracing, the operator API, `agentctl` and the
  web view, the evaluations and their results, and its Zarf package.

## Quickstart

Needs platform-lab v1.0+ (build cluster up, `make image` working) and
local-airgap-LLM v1.1+ (the endpoint deployed). From an empty machine,
all three repos in order:
[build guide](https://github.com/JGGHalfhide/platform-lab/blob/main/docs/build-guide.md).

```bash
make agent-image                       # reproducible image with crane (ADR 0004)
make -C ../platform-lab image IMAGE=oci-layout:$PWD/build/agent-image/oci \
  NAME=local-agents/agent:$(git rev-parse --short HEAD)   # SBOM, Trivy gate, cosign
# pin the printed digest in deploy/agents/status-reporter.yaml; Argo CD
# (platform-lab Application local-agents) syncs deploy/

kubectl -n agents port-forward svc/status-reporter 8080:8080 &
python3 agent/agentctl.py status       # or open http://localhost:8080/

KUBECONFIG=... eval/status/run_eval.py results/<name>   # fault-injection eval
make airgap-packages && make airgap-deploy             # the airgapped cluster
```

Details: [operator interface](docs/interface.md),
[eval](docs/eval-status.md), [airgap runbook](docs/airgap-runbook.md),
[image build](docs/image-build.md).

## Decisions

Architecture decision records: [docs/adr/](docs/adr/) (endpoint access,
runtime, the agent, image build, operator interface, scope, tools, tracing,
thinking, write actions).

## Timeline

| Week | Tag | What |
|---|---|---|
| 1 | v0.1 | VMs sized, endpoint access, eval set of 22 real incidents and the model-alone baseline, agent runtime chosen by a spike of five |
| 2 | v0.2 | The status reporter in the cluster: image, identity, tools, operator API and `agentctl`; first fault-injection eval 8/8, 5/5 |
| 3 | v0.3 | Eval follow-ups; no false findings |
| 4 | v0.4 | Tracing (OpenTelemetry, Tempo), prompts as GitOps files with an eval gate in CI, dashboard, thinking tested |
| 5 | v0.5 | The airgapped cluster: Zarf package, signatures via the Zarf registry, eval matching the build cluster |
| 6 | v1.0 | No write actions, prompt-injection cases, web view, results, recordings, build guide; both clusters rebuilt from fresh clones and evaluated |

## License

[MIT](LICENSE). Model weights are not in this repo; the model's source,
license and SHA-256 are recorded in local-airgap-LLM.
