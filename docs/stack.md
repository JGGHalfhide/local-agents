# Stack and pipeline

The full technical specification of local-agents: every tool and
component, its version, what it does here and why it was chosen; then the
pipeline from an incident to a triage answer, how data moves at run time,
and a diagram. Decisions are recorded in [adr/](adr/). Same structure as
local-airgap-LLM's and platform-lab's docs/stack.md.

The clusters come from
[platform-lab](https://github.com/JGGHalfhide/platform-lab) and the model
endpoint from
[local-airgap-LLM](https://github.com/JGGHalfhide/local-airgap-LLM); their
stack.md files describe them in full. This page lists them only for what
they do for the agents.

Rows marked *planned* are on the [roadmap](../ROADMAP.md) and not built yet.
Keep this page current every week.

## Tech stack

### Inherited

| Component | Version | What it does here | Why |
|---|---|---|---|
| Build host | GMKtec K8 Plus, Ryzen 7 8845HS (8 cores / 16 threads, AVX-512), ~28 GiB usable, Arch Linux | Runs both VMs (one at a time), the builds, the evaluation runs | Personal hardware |
| Clusters | platform-lab v1.0+: RKE2 1.36 (CIS), Argo CD, Zot, Kyverno, cosign, Prometheus/Grafana/Loki/Alloy, Velero, KEDA, Zarf | Where the agents run, connected and airgapped | Phase 1 |
| Model endpoint | local-airgap-LLM v1.1: llama-server (llama.cpp v1.0.0), Qwen3.5 4B Q4_K_M, `http://llm-api.llm.svc:8080` | OpenAI-compatible chat completions with tool calls and JSON output; thinking off unless a request opts in (1024-token budget) | Phase 2 |

### Agents (planned)

| Component | Version | What it does here | Why |
|---|---|---|---|
| Agent runtime | *planned, Week 1* (candidates measured offline: [scans/week1-runtime-footprint.txt](scans/week1-runtime-footprint.txt)) | | ADR 0002 |
| Tools | *planned, Week 2*: status reporter's read-only Kubernetes API tools (get/list/watch; pods, events, workloads, namespaces, nodes, PVCs, Argo CD Applications, KEDA objects), results capped | | [ADR 0003](adr/0003-first-agent-status-reporter.md) |
| Endpoint access | NetworkPolicy (Canal), no API key | Agent namespaces and agent pods labelled `inference.local-airgap-llm/client: "true"` (both required by the interceptor's policy); tools unlabelled | [ADR 0001](adr/0001-endpoint-access-networkpolicy-only.md) |
| Identity and policy | *planned, Week 2* | | |
| Retrieval: embedding model, vector store, index | *planned, Week 3* | | |
| Tracing | *planned, Week 4* | | |
| Evaluation set and scoring | v0: 22 cases (`eval/cases/`), `eval/check.py`, `eval/run_baseline.py`, `eval/review_sheet.py` | Real incidents from Phases 1-2 with known cause and fix; automatic first pass by patterns, then human review; leak check in CI | Decide by measurement; no judge model fits the lab ([eval.md](eval.md)) |
| Zarf packages | *planned, Week 5* | | |

## Pipeline

*To be written as it is built: evaluation set → agent image and config →
GitOps deploy → tools and retrieval → traced triage run → eval results →
airgap packages.*

## Data flow

*To be written: a triage request, tool calls, retrieval, model calls,
traces; what leaves which namespace (nothing leaves the cluster).*

## Diagram

*Mermaid, as in the other two repos, once the first agent runs (Week 2).*
