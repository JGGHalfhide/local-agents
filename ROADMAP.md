# local-agents roadmap

Goal: AI agents running inside the platform-lab Kubernetes platform and
calling local-airgap-LLM's in-cluster endpoint, with no internet: each agent
with its own identity (ServiceAccount, RBAC), tools behind NetworkPolicy and
Kyverno, prompts and tool configs versioned through GitOps, every model and
tool call traced, delivered through the same signed supply chain, and
deployed to the airgapped cluster. First agent: incident triage with
retrieval over platform-lab's and local-airgap-LLM's runbooks and docs.
Measured: answer quality on an evaluation set of real incidents, latency
and tokens per triage, with and without tools, retrieval and thinking.

Six weeks at about 7-10 hours per week. Each week ends with a rebuild check
and a tag, like the other two repos.

## Week 1: Foundations and the evaluation set

Goal: repo, sized VMs, decided endpoint access, and an evaluation set with
a baseline before any agent code. (v1.1 of local-airgap-LLM showed that
thinking, sampling and model choices cannot be judged without one.)

- [x] Git repo (GitHub), push the scaffold (README stub, LICENSE, .gitignore, .yamllint, CI); first CI run green (11/23)
- [ ] Resource plan: memory budget per node for the inference pod (5-6 GiB) + agents + tools + embedding model + vector store + tracing; resize the VMs in platform-lab if needed (still one at a time, ~28 GiB host). Record in docs/resource-plan.md.
- [ ] Endpoint access: keep NetworkPolicy-only, or add an API key (Vault) to llama-server? Decide (ADR); if yes, the change is made in local-airgap-LLM.
- [ ] Evaluation set v0: 15-25 triage cases from real incidents in Phases 1-2 with known causes and fixes (sources: platform-project.txt, local-airgap-LLM NOTES.txt and docs, e.g. the --cache-ram OOMKill, the moved postgres tag / digest NotFound, zarf init denied by Kyverno, KEDA restart scaling to zero, the inotify limit, Zarf's pull Secret in new namespaces, the etcd restore SELinux labels). Each case: input (alert, events, logs), expected cause, expected fix. Scoring method decided and written down.
- [ ] Baseline: the model alone on the eval set (no tools, no retrieval): thinking off vs on (1024 budget), greedy vs Qwen's recommended sampling. Latency and tokens per case.
- [ ] ADR 0001: agent runtime (a plain loop on the OpenAI-compatible API vs an agent framework), chosen by a small spike against the endpoint; footprint, airgap packaging, supply chain
- [ ] Tag v0.1

Acceptance: VMs sized and documented; endpoint access decided; an eval set with a measured baseline.

## Week 2: Tools, identity and policy

Goal: an agent in the cluster that uses read-only tools, under the
platform's policies.

- [ ] Tool interface: tools as functions in the agent vs separate tool servers (e.g. MCP); ADR
- [ ] First read-only tools: pod status, events and logs (Kubernetes API), a Prometheus query, a Loki query
- [ ] Identity: one ServiceAccount per agent and per tool server, RBAC read-only and namespace-scoped where possible; no Secrets in env
- [ ] NetworkPolicy: agent -> tools and llm-api only; tools -> their backends only; no egress; namespaces labelled as endpoint clients
- [ ] Images through platform-lab's `make image` (SBOM, Trivy gate, cosign), Kyverno verifies at admission; restricted Pod Security; Argo CD Application in platform-lab
- [ ] Smoke test: one eval case answered in-cluster with tool calls; unlabelled pod blocked; no egress; unsigned image rejected
- [ ] Tag v0.2

Acceptance: the agent answers a triage case with tools, in-cluster, passing the platform's policies as written or with documented scoped exceptions.

## Week 3: Retrieval

Goal: the agent finds the right runbook section.

- [ ] Embedding model chosen by measurement (openly licensed; served on CPU, e.g. llama.cpp's embedding mode; memory and speed); as a signed OCI image with provenance, following local-airgap-LLM's `make model`; ADR
- [ ] Vector store (e.g. pgvector on the platform's PostgreSQL vs a dedicated store): footprint, backups, airgap packaging; ADR
- [ ] Reproducible index build: docs from platform-lab and local-airgap-LLM pinned to commits, chunking recorded, rebuilt by a make target
- [ ] Retrieval eval: for each case, is the right document in the top k
- [ ] Context budget: retrieved chunks + tool output + prompt within the 32k shared context and a sane prompt-processing time (~110 tok/s)
- [ ] Tag v0.3

Acceptance: retrieval measured on the eval set; the index rebuilds from pinned sources.

## Week 4: Tracing, GitOps config, observability

Goal: every model and tool call visible; prompts change by commit.

- [ ] Trace every model call and tool call (OpenTelemetry; a trace backend that runs airgapped); ADR
- [ ] Decide what traces may contain (prompts, tool output, retrieved text), consistent with local-airgap-LLM's "no prompt content in Loki by default"; document
- [ ] Prompts and tool configs as versioned files synced by Argo CD; a prompt change is a commit, and the eval reruns on it
- [ ] Dashboard as code: runs, tool calls, latency, tokens, failures, thinking on/off
- [ ] Full eval run with tools + retrieval; compare with the Week 1 baseline; when thinking helps (per step type)
- [ ] Tag v0.4

Acceptance: a triage run is fully traced; eval results with tools and retrieval vs the baseline.

## Week 5: Airgap

Goal: the same agents on the disconnected VM.

- [ ] Zarf packages: agent, tools, embedding model (and its signatures), vector store and index, tracing, manifests, dashboard
- [ ] Packages built and signed on the build host; deployed with egress blocked via platform-lab's flow (after the cluster has settled post-boot)
- [ ] Signatures verified via the Zarf registry; unsigned image rejected; 0 pull errors
- [ ] Eval run on the airgapped cluster; results match the build cluster
- [ ] docs/airgap-runbook.md
- [ ] Tag v0.5

Acceptance: triage answers on the airgapped VM with egress blocked, everything verified, no pull errors.

## Week 6: Safety, results, publish

Goal: numbers, guardrails, and a repo a stranger can follow.

- [ ] Guardrails: tools read-only by default; any write action (e.g. restart a deployment) behind explicit approval or not offered (decide, ADR); prompt-injection test cases (instructions planted in logs and docs)
- [ ] Results: accuracy, latency and tokens per triage, with/without tools, retrieval and thinking; concurrency with the endpoint's 4 slots
- [ ] README: architecture (Mermaid), results table, quickstart (depends on platform-lab v1.0+ and local-airgap-LLM v1.1+)
- [ ] docs/stack.md complete; ADRs complete; gitleaks; employer check
- [ ] Full rebuild of both clusters from fresh clones of all three repos; record times
- [ ] Tag v1.0; post (user's)

Acceptance: a fresh clone of the three repos reproduces the agents on both clusters, with eval results.

## Open questions

- Endpoint access: NetworkPolicy only, or an API key from Vault (Week 1)? Changes go in local-airgap-LLM.
- VM size: how much more than 16 GiB per VM do agents, embeddings, a vector store and tracing need, still running one VM at a time (Week 1)?
- When should an agent opt in to thinking (per step type), with which sampling settings (Qwen recommends sampling, not greedy, in thinking mode), and should reasoning be kept across turns (`--reasoning-preserve`, context growth)? Answered by the eval set (Weeks 1 and 4).
- One model or two: is Qwen3.5 4B enough for triage, or does a larger model for hard steps earn its memory? (Week 1 baseline, Week 4)
- Agent runtime: plain loop vs a framework; tools in-process vs tool servers (MCP) (Weeks 1-2).
- Concurrency: the endpoint has 4 slots shared with every client; an agent run is many calls. Queueing, priorities, a second replica (does not fit today)?
- Write actions: offered at all, and how approved (Week 6)?
- What may traces contain (Week 4)?
- iGPU (Radeon 780M, Vulkan): deferred; only if CPU speed limits the agents.
- platform-lab: re-running `zarf init` under the Kyverno policies is planned there (scoped exception during init); until then an interrupted init on the airgap VM means a fresh VM.
