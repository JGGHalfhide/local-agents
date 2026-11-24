# local-agents

AI agents running inside the
[platform-lab](https://github.com/JGGHalfhide/platform-lab) Kubernetes
platform, calling the CPU-only, airgapped LLM endpoint from
[local-airgap-LLM](https://github.com/JGGHalfhide/local-airgap-LLM): per-agent
identity, read-only tools behind NetworkPolicy and Kyverno, retrieval over
the platform's runbooks, every model and tool call traced, delivered through
the same signed supply chain and deployed to an airgapped cluster with no
internet. First agent: incident triage, measured on an evaluation set of
real incidents.

**Status:** Week 0: planning. See [ROADMAP.md](ROADMAP.md).

## How it fits

- **platform-lab** provides the clusters: VMs (Terraform), OS hardening,
  RKE2, Argo CD, Zot, Kyverno, cosign, monitoring, Velero, KEDA, Zarf.
- **local-airgap-LLM** provides the model endpoint: Qwen3.5 4B on
  llama.cpp, OpenAI-compatible, scale to zero, the model as a signed image.
- **This repo** provides the agents: agent workloads and their identity,
  tools, retrieval, prompts and tool configs, tracing, the evaluation set and
  results, and the Zarf packages for the airgapped cluster.

## Decisions

Architecture decision records are in [docs/adr/](docs/adr/). Every tool,
its version and why: [docs/stack.md](docs/stack.md).

## License

[MIT](LICENSE). Model weights and indexes are not in this repo; each
model's source, license and SHA-256 are recorded in the docs.
