# local-agents roadmap

Goal: AI agents running inside the platform-lab Kubernetes platform and
calling local-airgap-LLM's in-cluster endpoint, with no internet: each agent
with its own identity (ServiceAccount, RBAC), tools behind NetworkPolicy and
Kyverno, prompts and tool configs versioned through GitOps, every model and
tool call traced, delivered through the same signed supply chain, and
deployed to the airgapped cluster. Agent 1: a read-only platform status
reporter (ADR 0003), scored automatically by fault injection in disposable
namespaces (docs/eval-status.md). Agent 2 (stretch): incident triage with
known-issue retrieval, measured on the evaluation set of real incidents
(docs/eval.md). Measured: detection, location and classification of
injected faults, grounding and tool-call validity, latency and tokens per
run, run-to-run variance; for agent 2, answer quality with and without
retrieval and thinking.

Six weeks at about 7-10 hours per week. Each week ends with a rebuild check
and a tag, like the other two repos.

## Week 1: Foundations and the evaluation set

Goal: repo, sized VMs, decided endpoint access, and an evaluation set with
a baseline before any agent code. (v1.1 of local-airgap-LLM showed that
thinking, sampling and model choices cannot be judged without one.)

- [x] Git repo (GitHub), push the scaffold (README stub, LICENSE, .gitignore, .yamllint, CI); first CI run green (11/23)
- [x] Resource plan: memory budget per node for the inference pod (5-6 GiB) + agents + tools + embedding model + vector store + tracing; resize the VMs in platform-lab if needed (still one at a time, ~28 GiB host). Record in docs/resource-plan.md. (11/23: both VMs 12 vCPU / 20 GiB, applied and measured.)
- [x] Endpoint access: keep NetworkPolicy-only, or add an API key (Vault) to llama-server? Decide (ADR); if yes, the change is made in local-airgap-LLM. (11/23: NetworkPolicy only, ADR 0001; no change to local-airgap-LLM.)
- [x] Evaluation set v0: 15-25 triage cases from real incidents in Phases 1-2 with known causes and fixes (sources: platform-project.txt, local-airgap-LLM NOTES.txt and docs, e.g. the --cache-ram OOMKill, the moved postgres tag / digest NotFound, zarf init denied by Kyverno, KEDA restart scaling to zero, the inotify limit, Zarf's pull Secret in new namespaces, the etcd restore SELinux labels). Each case: input (alert, events, logs), expected cause, expected fix. Scoring method decided and written down. (11/23: v0, 22 cases, docs/eval.md; scoring: pattern first pass + human review, accepted.)
- [x] Baseline: the model alone on the eval set (no tools, no retrieval): thinking off vs on (1024 budget), greedy vs Qwen's recommended sampling. Latency and tokens per case. (Run 11/23, scores final 11/24: docs/eval.md.)
- [x] ADR 0003: first agent = read-only platform status reporter, scored by fault injection; triage becomes agent 2 (11/24)
- [ ] ADR 0002: agent runtime (a plain loop on the OpenAI-compatible API vs an agent framework), chosen by a small spike against the endpoint whose task is the status reporter's tool loop (read-only Kubernetes tools, capped results); footprint, airgap packaging, supply chain, backend-neutral client config (base URL, model, key)
- [x] Fault-injection eval spec (docs/eval-status.md) and inject/cleanup stubs; approved 11/24 (8 faults, 5 controls, f09 dropped, context caps); nothing injected yet
- [ ] Tag v0.1

Acceptance: VMs sized and documented; endpoint access decided; an eval set with a measured baseline.

## Week 2: Agent 1 (status reporter): tools, identity and policy

Goal: the status reporter in the cluster, using read-only Kubernetes API
tools under the platform's policies, scored by fault injection.

- [ ] Image build path: nothing in the lab builds images yet (platform-lab `make image` republishes upstream images; no podman/docker/buildah on the host, found 11/23). Decide how agent and tool images are built reproducibly (e.g. buildah or podman on the host, pinned base by digest), then through `make image`; likely a platform-lab change
- [ ] Tool interface: tools as functions in the agent vs separate tool servers (e.g. MCP); ADR
- [ ] First read-only tools (Kubernetes API, get/list/watch): pods, events, workloads, namespaces, nodes, PVCs, Argo CD Applications, KEDA objects; every result capped and summarised within a per-run input budget (docs/eval-status.md). Pod logs not in v1; a safe way to add them proposed. Prometheus and Loki queries later
- [ ] Identity: the status reporter's own ServiceAccount and ClusterRole (get/list/watch only on the resources above; no Secrets, no pods/exec, no pods/log in v1); one ServiceAccount per tool server if any; no Secrets in env
- [ ] NetworkPolicy: agent -> tools and llm-api only; tools -> their backends only; no egress; namespaces labelled as endpoint clients
- [ ] Images through platform-lab's `make image` (SBOM, Trivy gate, cosign), Kyverno verifies at admission; restricted Pod Security; Argo CD Application in platform-lab
- [ ] Fault-injection eval run (approved faults and controls only, in `agent-eval-*` namespaces): automatic scores; greedy repeated to check determinism, any sampled configuration run 3 times
- [ ] Smoke test: a status report in-cluster with tool calls; unlabelled pod blocked; no egress; unsigned image rejected; the agent's ServiceAccount denied Secrets, pods/exec and pods/log
- [ ] Tag v0.2

Acceptance: the status reporter runs in-cluster with read-only tools, passing the platform's policies as written or with documented scoped exceptions, with automatic fault-injection scores.

## Week 3: Agent 2 (triage, stretch): known-issue retrieval

Goal: the triage agent finds the matching known issue or runbook section.

- [ ] Embedding model chosen by measurement (openly licensed; served on CPU, e.g. llama.cpp's embedding mode; memory and speed); as a signed OCI image with provenance, following local-airgap-LLM's `make model`; ADR
- [ ] Vector store (e.g. pgvector on the platform's PostgreSQL vs a dedicated store): footprint, backups, airgap packaging; ADR
- [ ] Reproducible index build: known issues and docs from platform-lab and local-airgap-LLM pinned to commits, chunking recorded, rebuilt by a make target; 6-8 incidents of the evaluation set held out of the index (chosen and recorded before the first build)
- [ ] Retrieval eval: for each case, is the right document in the top k; held-out incidents reported separately
- [ ] Context budget: retrieved chunks + tool output + prompt within the 32k shared context and a sane prompt-processing time (~110 tok/s)
- [ ] Tag v0.3

Acceptance: retrieval measured on the eval set; the index rebuilds from pinned sources.

## Week 4: Tracing, GitOps config, observability

Goal: every model and tool call visible; prompts change by commit.

- [ ] Trace every model call and tool call (OpenTelemetry; a trace backend that runs airgapped); ADR
- [ ] Decide what traces may contain (prompts, tool output, retrieved text), consistent with local-airgap-LLM's "no prompt content in Loki by default"; document
- [ ] Prompts and tool configs as versioned files synced by Argo CD; a prompt change is a commit, and the eval reruns on it
- [ ] Dashboard as code: runs, tool calls, latency, tokens, failures, thinking on/off
- [ ] Thinking: per-request opt-in tested on the status reporter, only after agent 1 works with thinking off (off stays the default)
- [ ] Agent 2 (if built): eval run with retrieval; compare with the Week 1 baseline
- [ ] Tag v0.4

Acceptance: a status-reporter run is fully traced; fault-injection results with thinking off vs opted in.

## Week 5: Airgap

Goal: the same agents on the disconnected VM.

- [ ] Zarf packages: agent, tools, embedding model (and its signatures), vector store and index, tracing, manifests, dashboard
- [ ] Packages built and signed on the build host; deployed with egress blocked via platform-lab's flow (after the cluster has settled post-boot)
- [ ] Signatures verified via the Zarf registry; unsigned image rejected; 0 pull errors
- [ ] Eval run on the airgapped cluster; results match the build cluster
- [ ] docs/airgap-runbook.md
- [ ] Tag v0.5

Acceptance: status reports (and triage answers, if built) on the airgapped VM with egress blocked, everything verified, no pull errors.

## Week 6: Safety, results, publish

Goal: numbers, guardrails, and a repo a stranger can follow.

- [ ] Guardrails: tools read-only by default; any write action (e.g. restart a deployment) behind explicit approval or not offered (decide, ADR); prompt-injection test cases (instructions planted in logs and docs)
- [ ] Results: fault-injection scores, latency and tokens per run, variance, thinking off vs on; triage with/without retrieval if built; concurrency with the endpoint's 4 slots
- [ ] README: architecture (Mermaid), results table, quickstart (depends on platform-lab v1.0+ and local-airgap-LLM v1.1+)
- [ ] docs/stack.md complete; ADRs complete; gitleaks; employer check
- [ ] Full rebuild of both clusters from fresh clones of all three repos; record times
- [ ] Tag v1.0; post (user's)

Acceptance: a fresh clone of the three repos reproduces the agents on both clusters, with eval results.

## Open questions

- ~~Endpoint access: NetworkPolicy only, or an API key from Vault (Week 1)? Changes go in local-airgap-LLM.~~ Answered 11/23: NetworkPolicy only (ADR 0001).
- ~~VM size: how much more than 16 GiB per VM do agents, embeddings, a vector store and tracing need, still running one VM at a time (Week 1)?~~ Answered 11/23: 12 vCPU / 20 GiB, one at a time (docs/resource-plan.md); estimates replaced by measurements in Weeks 2-4. Disk on build-node-01 (69%) is the next limit.
- When should an agent opt in to thinking (per step type), with which sampling settings (Qwen recommends sampling, not greedy, in thinking mode), and should reasoning be kept across turns (`--reasoning-preserve`, context growth)? Off by default; opt-in tested on the status reporter only after it works (Week 4).
- Pod logs for the status reporter: how to add them safely (size caps, redaction, which namespaces) after v1 (Week 2 proposal).
- One model or two: is Qwen3.5 4B enough, or does a larger model for hard steps earn its memory? The client is backend-neutral, so the same fault-injection eval can later run against a hosted model for comparison (not planned yet). (Week 1 baseline, Week 4)
- Agent runtime: plain loop vs a framework; tools in-process vs tool servers (MCP) (Weeks 1-2).
- Concurrency: the endpoint has 4 slots shared with every client; an agent run is many calls. Queueing, priorities, a second replica (does not fit today)?
- Write actions: offered at all, and how approved (Week 6)?
- What may traces contain (Week 4)?
- iGPU (Radeon 780M, Vulkan): deferred; only if CPU speed limits the agents.
- platform-lab: re-running `zarf init` under the Kyverno policies is planned there (scoped exception during init); until then an interrupted init on the airgap VM means a fresh VM.
