# Architecture decision records

Each record states one decision and its context: `NNNN-title.md`, a
`Status: accepted (Week N, MM/DD)` line, then `## Context` (the options,
with measurements where they decided it) and `## Decision`. Same format as
platform-lab and local-airgap-LLM. A later change gets a new record that
refers to the old one; old records keep the numbers from when they were
decided.

| # | Decision |
|---|---|
| [0001](0001-endpoint-access-networkpolicy-only.md) | Endpoint access: NetworkPolicy only, no API key (Week 1) |
| [0003](0003-first-agent-status-reporter.md) | First agent: read-only platform status reporter, scored by fault injection; triage becomes agent 2 (Week 1) |

Expected in the first weeks (ROADMAP.md): agent runtime (0002, Week 1), tool
interface (Week 2), embedding model and vector store (Week 3), tracing
(Week 4), write actions and approval (Week 6).
