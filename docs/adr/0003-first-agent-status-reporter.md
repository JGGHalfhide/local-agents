# 0003. First agent: a read-only platform status reporter

Status: accepted (Week 1, 11/24)

## Context

The roadmap made incident triage the first agent, with retrieval over the
platform's runbooks, measured on the evaluation set v0 (22 reconstructed
incidents, [eval.md](../eval.md)). That set is scored by patterns plus a
human review of every proposed 0, every harmful flag and one in four of the
2s. The Week 1 baseline (4 configurations x 22 cases = 88 answers) needed
80 answers reviewed by hand. Every later configuration (tools, retrieval,
thinking, the airgapped run) would need the same, and sampled
configurations need repeat runs.

A status reporter answers a narrower question: what is wrong in the
cluster now, where, and of which kind. With read-only access to the
Kubernetes API, its answers can be checked against the cluster itself:
inject a known fault in a disposable namespace, run the agent, compare.
Scoring is then automatic and repeatable (detect, locate, classify,
grounding in tool output, valid tool calls), so variance across runs can be
measured at no review cost.

It uses the parts every later agent needs (an identity, read-only tools,
the tool loop against the endpoint, tracing, the airgap packages), with
less risk: get/list/watch only, no Secrets, no pod logs in its first
version.

## Decision

- Agent 1 is a read-only platform status reporter (Week 2: tools and
  identity). It reports faults it can see through the Kubernetes API, each
  with namespace, object and one category from a closed set.
- It is scored automatically by fault injection: faults are created only in
  disposable `agent-eval-*` namespaces (platform components only with the
  user's approval of the specific fault), alongside healthy controls the
  agent must report as no fault. Spec: docs/eval-status.md (proposed;
  nothing injected before the user approves it).
- Its identity: its own ServiceAccount; a ClusterRole with get, list and
  watch only, on pods, events, workloads, namespaces, nodes, PVCs, Argo CD
  Applications and KEDA objects. No Secrets, no `pods/exec`; `pods/log`
  excluded from the first version.
- Agent 2 is incident triage (stretch), with known-issue retrieval in
  Week 3; 6-8 incidents are held out of the index to test it. The evaluation
  set v0 and its Week 1 baseline stay as agent 2's measure.
- ADR 0002's runtime spike uses the status reporter's tool loop as its task.
- Thinking stays off by default; per-request opt-in is tested only after
  agent 1 works.
- Endpoint access is unchanged (ADR 0001). The agent's client takes base
  URL, model and key from config, so the same evaluation can run against
  another OpenAI-compatible backend; no such run is part of this decision.
