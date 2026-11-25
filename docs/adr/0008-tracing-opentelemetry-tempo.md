# 0008. Tracing: OpenTelemetry SDK in the agent, Grafana Tempo in platform-lab, metadata only

Status: accepted (Week 4, 11/25)

## Context

The roadmap asks for every model call and tool call to be traced, with a
backend that runs airgapped, and for a decision on what traces may
contain. Before Week 4 the run object (GET /v1/runs/{id}, ADR 0005) held
the tool-call trace and total timings for the last 50 runs, in an emptyDir:
no per-model-call timing or token counts, nothing kept across pod restarts,
nothing Grafana could show.

platform-lab (11/25) had Prometheus, Grafana, Loki and Alloy, and no trace
store.

| | Grafana Tempo 3.1.1 | Jaeger 2.23 |
|---|---|---|
| Chart | grafana-community/tempo 3.2.1 (single binary; the grafana/helm-charts copy is deprecated) | jaegertracing/jaeger 4.20.0 |
| Storage | Filesystem on a local-path volume, like Loki | Badger or memory in all-in-one |
| UI | A datasource in the Grafana that already runs (dashboards as code, Week 4) | A second UI to run and expose |
| Airgap | One upstream image, pinned by digest, in platform-lab's Zarf monitoring package with Loki and Alloy | Same effort |

For the agent side (measured offline, 11/25):

| | OpenTelemetry SDK + OTLP/HTTP exporter 1.45.2 | OTLP/JSON by hand (stdlib) |
|---|---|---|
| Dependencies | 14 more locked wheels (14 -> 28), ~1.9 MiB of wheels; Trivy result of the image unchanged (0 CRITICAL, 61 HIGH / 8 fixable, all from the base) | None |
| Code | agent/tracing.py (setup, flush) + spans in agent/loop.py | A span encoder, batching and retries to write and test |
| Conventions | Standard SDK, GenAI semantic conventions; a stranger knows it | Ours |

The user chose Tempo and the SDK (11/25).

What traces may contain: local-airgap-LLM decided that no prompt or
response content goes into Loki by default (docs/observability.md there).
A status run's prompts are fixed in the image (their SHA-256 identifies
them), and its tool results are cluster state already readable through the
run object under RBAC (pods/portforward); copying them into Tempo would add
a second, wider-read store (anyone with Grafana) for no debugging gain the
run object does not give.

Measured (docs/scans/week4-tracing.txt; platform-lab 62262d6, image
e06d4f4): one status run through agentctl, 47.7 s, gave one trace of 18
spans (run, 9 model calls, 8 tool calls), 8.2 KiB of OTLP; per-call
latency and tokens visible (the final structured request: 22.3 s of the
47.7 s); no prompt, user message or tool-result text in the stored trace.
Tempo: 29 MiB idle, 152 MiB after the run, 2-4m CPU (request 128 MiB,
limit 512 MiB), against the 200-500 MiB estimated.

## Decision

- **Backend: Grafana Tempo 3.1.1, single binary, in platform-lab**
  (gitops/apps/tempo.yaml, gitops/values/tempo.yaml; 62262d6): namespace
  `monitoring`, filesystem on a 2 Gi local-path volume, 7 days, OTLP/HTTP
  receiver only (:4318), usage reporting off, no ServiceAccount token,
  restricted security context; a Grafana datasource; the image in the
  platform-bootstrap-images exception like Loki and Alloy; a component in
  platform-lab's Zarf monitoring package for the airgap.
- **Agent: the OpenTelemetry SDK with the OTLP/HTTP exporter**
  (agent/tracing.py), on only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set
  (the Deployment sets `http://tempo.monitoring.svc:4318`; egress allowed to
  Tempo pods on 4318 only). One trace per run: `invoke_agent
  status-reporter`, with a `chat <model>` span per model call and an
  `execute_tool <tool>` span per tool call, named after the GenAI semantic
  conventions. Spans are flushed at the end of each run. The run object
  carries `trace_id`.
- **Traces carry metadata only**: model and request settings, token counts,
  finish reasons, tool names, argument keys (not values), result sizes,
  errors, timings, run id, status and counts, the system prompt's SHA-256.
  No prompt or user text, no model output, no tool argument values, no tool
  result text. The run object stays the place for content. Adding content
  to traces needs a new ADR.
- Not traced: the HTTP server and agentctl (the run span covers the work);
  no auto-instrumentation of the openai or HTTP libraries (it would record
  request bodies by default in some versions).
