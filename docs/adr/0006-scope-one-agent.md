# 0006. Scope: one agent, no triage agent

Status: accepted (Week 2, 11/24)

## Context

ADR 0003 made the read-only status reporter agent 1 and kept incident
triage with known-issue retrieval as agent 2, a stretch goal for Week 3.
By the end of Week 2 the status reporter runs in the cluster under its own
identity, behind an operator API (ADR 0005), and passes its fault-injection
eval (8/8 faults, 5/5 controls). The project's aim is the
whole lab working end to end across the three repos: an airgapped cluster (platform-lab), a
locally hosted LLM (local-airgap-LLM), and an agent that uses it (this
repo).

## Decision

No triage agent (the user's decision, 11/24). The status reporter is the
only agent. Dropped from the plan: retrieval (embedding model, vector store,
index, held-out incidents) and the triage eval runs. The evaluation set v0
and its Week 1 baseline (docs/eval.md, results/week1-baseline/) stay as the
record of the model-alone measurement; no further use is planned. The
remaining weeks serve the status reporter: its follow-ups, tracing, the
airgap deployment and the results.
