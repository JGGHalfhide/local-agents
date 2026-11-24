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
| [0002](0002-agent-runtime-plain-openai-loop.md) | Agent runtime: a plain tool loop on the openai SDK, chosen by a spike of 5 runtimes (Week 1) |
| [0003](0003-first-agent-status-reporter.md) | First agent: read-only platform status reporter, scored by fault injection; triage becomes agent 2 (Week 1) |

Expected in the next weeks (ROADMAP.md): tool interface and image build
(Week 2), embedding model and vector store (Week 3), tracing
(Week 4), write actions and approval (Week 6).
