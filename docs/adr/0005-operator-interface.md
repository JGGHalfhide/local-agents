# 0005. Operator interface: HTTP API v1, agentctl, read-only web view

Status: accepted (Week 2, 11/24)

## Context

The status reporter (ADR 0003) runs today as an hourly CronJob that prints
one JSON report to its log; an operator reads it with `kubectl logs`, and
the fault-injection scorer (docs/eval-status.md) has no defined way to start
a run and read the result. The user asked for an operator interface: a
structured API, a command-line client and a read-only web view, with one
path shared by operators and the eval.

Constraints from the repo:

- The endpoint's 32k KV pool is shared by its 4 slots
  (docs/scans/week1-llm-slots.txt); an agent run holds up to ~7k tokens per
  turn and takes 76-142 s in-cluster (docs/scans/week2-*), more on a cold
  start (~6 s from zero).
- Airgap: no CDN or external assets; every dependency pinned and vendored.
  The agent image already has Python 3.14 and the standard library (ADR 0004).
- Access to the endpoint is NetworkPolicy only, no API key (ADR 0001); the
  agent's identity is read-only (ADR 0003).
- `kubectl port-forward` reaches a pod through the kubelet inside the pod's
  network namespace, so NetworkPolicy does not filter it; RBAC on
  `pods/portforward` does.
- Model output is untrusted text (the tools pass cluster data, including
  event messages, to the model).

## Decision

As specified in [interface.md](../interface.md):

- **API v1**, served by the agent image (`python -m agent serve`, standard
  library `http.server`) as a Deployment and ClusterIP Service in `agents`:
  `POST /v1/status` (optional namespace, thinking flag default off),
  `GET /v1/runs`, `GET /v1/runs/{id}`, `GET /healthz`. Synchronous; the
  server stops a run at 300 s, clients wait 330 s. One run at a time, a
  second request gets 429 with `Retry-After`. The last 50 runs are kept in a
  64 MiB emptyDir.
- **Run object**: run_id, status (healthy | fault | unknown), findings with
  the 10 categories of docs/eval-status.md and evidence that names tool-call
  ids with verbatim excerpts, the tool calls (id, tool, arguments, result
  truncated to 2,000 characters, duration), model settings, timings.
  Grounding is the scorer's check: a finding whose object does not appear in
  a tool result, or whose excerpt is not in the cited result, is moved to
  `ungrounded`.
- **One path**: the CronJob and the fault-injection scorer call the same
  endpoint (the CronJob with agentctl in the cluster, the scorer through
  port-forward).
- **agentctl**: one Python file, standard library only. `status [-n]`,
  `runs`, `trace RUN_ID`, `health`; `--json`, `--thinking`, `--timeout`,
  `--endpoint`. Exit 0 healthy, 1 fault, 2 error or unknown.
- **Web view**: read-only, served by the same server from the same JSON;
  server-rendered HTML, no JavaScript, one vendored CSS file; every value
  HTML-escaped, no markdown or HTML rendering of model text; a strict
  Content-Security-Policy; no forms or write actions. Demo mode serves
  recorded runs under a fixed DEMO banner and refuses `POST /v1/status`.
- **Access**: NetworkPolicy admits ingress to the server only from the
  CronJob's agentctl pods; operators and the scorer use `kubectl
  port-forward`, gated by RBAC (`get`/`list` services and pods,
  `create pods/portforward` in `agents`). No API key or login.
- **Scheduling**: API and agentctl in Week 2 (the scorer needs them); the
  web view is a Week 5-6 stretch.

Revisit (new ADR) if: a second user or untrusted workload appears, the
interface is exposed beyond port-forward (an Ingress), or runs must survive
pod restarts.
