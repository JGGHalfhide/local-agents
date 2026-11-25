# Operator interface: API v1, agentctl, web view

Status: **planned** (Week 2, 11/24; [ADR 0005](adr/0005-operator-interface.md)).
Nothing here is implemented yet.

One path for everyone: the status reporter runs only through the API below.
Operators call it with `agentctl` or read it in the web view; the hourly
CronJob calls it with `agentctl`; the fault-injection scorer
(docs/eval-status.md) calls the same endpoint and scores the same JSON.

## Where it runs

| Part | What |
|---|---|
| Server | The agent image (ADR 0004) runs `python -m agent serve`: Python standard library `http.server` (threaded), no new dependency. A Deployment `status-reporter` (1 replica) and a ClusterIP Service `status-reporter:8080` in namespace `agents`. |
| Run history | An `emptyDir` volume (`sizeLimit: 64Mi`) holding the last 50 runs as JSON files; lost when the pod restarts (by design: no PVC, no Secrets). |
| Schedule | The existing CronJob becomes `agentctl status` against the Service (same image), so scheduled runs use the API too. |
| Identity | Unchanged: ServiceAccount `status-reporter`, read-only ClusterRole (ADR 0003). The CronJob's pod gets no ServiceAccount token (it only calls the API). |

## API v1

Base URL: `http://status-reporter.agents.svc:8080` in the cluster;
`http://127.0.0.1:8080` through `kubectl port-forward`. JSON in and out,
`Content-Type: application/json`.

### `POST /v1/status`

Starts one run and answers when it is done (synchronous).

Request body (all fields optional):

```json
{"namespace": "agent-eval-f04", "thinking": false}
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `namespace` | string or null | null (whole cluster) | Restrict the tools to one namespace (cluster-scoped tools such as `list_nodes` still answer). |
| `thinking` | bool | false | Per-request thinking opt-in (`chat_template_kwargs: {"enable_thinking": true}`, server budget 1024 tokens). Untested for the status reporter until Week 4 (CLAUDE.md); off by default. |

Responses:

| Code | When | Body |
|---|---|---|
| 200 | Run finished (any outcome, including `unknown`) | Run object |
| 400 | Body is not JSON, unknown field, wrong type | `{"error": "..."}` |
| 429 | A run is already in progress | `{"error": "busy", "run_id": "<running>"}`, header `Retry-After: 30` |
| 504 | Run deadline exceeded | Run object with `status: "unknown"`, `error: "deadline exceeded"` |

Timeouts: the server stops a run at **300 s** (cold start ~6 s from zero,
measured runs 76-142 s in-cluster, slowest spike run 364 s with the old
loop; the turn cap bounds it). Clients wait **330 s** by default. The KEDA
interceptor route has no response timeout (local-airgap-LLM stack.md), so it
does not cut a long run.

Concurrency: **one run at a time**; a second request gets 429 (no queue).
The endpoint's 32k KV pool is shared by its 4 slots (docs/scans/week1-llm-slots.txt);
one agent run already holds up to ~7k tokens per turn.

### `GET /v1/runs`

The last 50 runs, newest first: `[{"run_id", "started", "status",
"namespace", "findings": <count>, "seconds", "demo"}]`.

### `GET /v1/runs/{run_id}`

One run object (below), or 404.

### `GET /healthz`

`200 {"ok": true, "version": "...", "busy": false, "runs_kept": 12}`.
No model call and no API-server call: it says the server is up, not that
the endpoint is (the endpoint is at zero most of the time).

### Run object

```json
{
  "run_id": "r-20261124T230107Z-3f9a",
  "status": "fault",
  "demo": false,
  "namespace": null,
  "findings": [
    {
      "namespace": "agent-eval-f04",
      "object": "Pod/crashy-6d8f9c7b5-x2kqp",
      "category": "crash-loop",
      "summary": "Container exits 127 and restarts (CrashLoopBackOff).",
      "evidence": [
        {"tool_call_id": "t3", "excerpt": "crashy-6d8f9c7b5-x2kqp\tRunning\t0/1\t6\tCrashLoopBackOff\tError(127)"}
      ]
    }
  ],
  "ungrounded": [],
  "tool_calls": [
    {"id": "t3", "tool": "list_pods", "arguments": {}, "result": "pods\nnamespace\tname...",
     "result_chars": 3379, "truncated": true, "duration_ms": 41, "error": false}
  ],
  "model": {"name": "qwen3.5-4b", "base_url": "http://llm-api.llm.svc:8080/v1",
            "temperature": 0, "max_tokens": 1024, "thinking": false,
            "max_tool_calls": 8, "max_turns": 10, "prompt_sha256": "..."},
  "timings": {"started": "2026-11-24T23:01:07Z", "finished": "2026-11-24T23:03:29Z",
              "total_s": 142.0, "model_s": 139.6, "tools_s": 0.4, "turns": 4},
  "error": null
}
```

| Field | Meaning |
|---|---|
| `status` | `healthy`: a valid report with no findings. `fault`: one or more findings. `unknown`: no valid report (endpoint error, deadline, no tool call, every finding ungrounded). |
| `findings[].object` | `Kind/name`. |
| `findings[].category` | One of the 10 in docs/eval-status.md: `scaled-to-zero`, `image-pull`, `crash-loop`, `oom-killed`, `admission-denied`, `unschedulable`, `storage-unbound`, `gitops-unhealthy`, `node-not-ready`, `other`. |
| `findings[].evidence[]` | Each item names a tool call by id and quotes an excerpt of its result. |
| `ungrounded` | Findings dropped by the grounding check, kept for review. |
| `tool_calls[].result` | The first 2,000 characters of what the model saw (`result_chars` is the full length, up to the 3,500-character tool cap). |
| `model` | Settings actually used. No key: the endpoint needs none (ADR 0001); a hosted backend's key would come from a Secret and never appear here. |

Grounding (the same check the scorer uses): a finding is kept only if its
namespace (when set) and object name appear in the result of at least one
tool call of the run, and each evidence excerpt appears verbatim in the
result of the tool call it names (compared on the full result, before
truncation). Otherwise the finding moves to `ungrounded`.

Deterministic rule (from the step 3 smoke test): a `scaled-to-zero` finding
on a workload that `list_workloads` marks as scaled by KEDA is dropped
before grounding and counted in `ungrounded` with the reason.

## agentctl

A single-file Python 3 command (`agent/agentctl.py`, also installed in the
image), standard library only (`argparse`, `urllib`, `json`), so it copies
into the airgap with nothing to vendor.

| Command | Calls | Prints |
|---|---|---|
| `agentctl status [-n NAMESPACE]` | `POST /v1/status` | The report: status line, each finding with its evidence trail (tool call, excerpt), ungrounded findings, timings |
| `agentctl runs` | `GET /v1/runs` | A table of recent runs |
| `agentctl trace RUN_ID` | `GET /v1/runs/{id}` | Every tool call in order: tool, arguments, duration, the result excerpt |
| `agentctl health` | `GET /healthz` | Up/busy, version, runs kept |

Flags: `--json` (print the API's JSON unchanged), `--thinking` (status
only), `--timeout SECONDS` (default 330), `--endpoint URL` (default
`$AGENTCTL_ENDPOINT`, else `http://127.0.0.1:8080`).

Exit codes: **0** healthy, **1** fault found, **2** error or unknown (also
504, connection failure, bad arguments), **3** busy (429: another run in
progress, nothing was run; Week 3, so the CronJob counts it as a skipped
run). `runs`, `trace` and `health` exit 0 on success, 2 on error.

Operator use: `kubectl -n agents port-forward svc/status-reporter 8080:8080`
in one terminal, `agentctl status` in another.

## Web view

Read-only HTML served by the same server, rendered from the same run JSON:

| Path | Shows |
|---|---|
| `GET /` | Recent runs (as `GET /v1/runs`) |
| `GET /runs/{run_id}` | One run: status, findings with evidence linked to their tool calls, ungrounded findings, the tool-call trace, model settings, timings |
| `GET /static/view.css` | The only asset, served from the image |

Rules:

- Rendered on the server, no JavaScript; one CSS file from the image. No
  CDN, no external fonts, scripts or images (airgap).
- Model output is untrusted: every value is HTML-escaped
  (`html.escape`); no markdown or HTML rendering of model text; tool output
  shown in `<pre>` as escaped text.
- Headers on every page: `Content-Security-Policy: default-src 'none';
  style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none';
  frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`.
- No forms, no write actions, no way to start a run from the browser (runs
  start only through `POST /v1/status`). No Secret values exist in the run
  JSON to show.
- Demo mode (recommended): `AGENT_DEMO_RUNS=<dir>` serves recorded run JSON
  instead of live runs, every page carries a fixed red **DEMO: recorded run,
  not the live cluster** banner, and API responses carry `"demo": true`. In
  demo mode `POST /v1/status` answers 409, so a demo can never be mistaken
  for a live report. Recorded runs come from the fault-injection eval, so
  screenshots need no live fault.

## Access

NetworkPolicy, as for the endpoint (ADR 0001): no API key, no login.

- Ingress to the server pod on 8080: only from pods in `agents` labelled
  `app.kubernetes.io/name: agentctl` (the CronJob). Nothing else in the
  cluster can reach it.
- `kubectl port-forward` is not filtered by NetworkPolicy (the kubelet opens
  the connection inside the pod's network namespace). The gate for operators
  and the scorer is RBAC on `pods/portforward`:

```yaml
# Role in namespace agents, bound to the operator (user or group)
rules:
  - apiGroups: [""]
    resources: [services, pods]
    verbs: [get, list]          # port-forward svc/... resolves to a pod
  - apiGroups: [""]
    resources: [pods/portforward]
    verbs: [create]
```

  Today the only operator is the admin kubeconfig, which already has this;
  the Role is for a non-admin operator later.

## Documentation (vendor first; videos: none confirmed)

- Python `http.server` (the docs warn it is not for production; fine for a
  single-user lab): https://docs.python.org/3/library/http.server.html
- `urllib.request`: https://docs.python.org/3/library/urllib.request.html,
  `argparse`: https://docs.python.org/3/library/argparse.html,
  `html.escape`: https://docs.python.org/3/library/html.html
- `kubectl port-forward`: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_port-forward/,
  task: https://kubernetes.io/docs/tasks/access-application-cluster/port-forward-access-application-cluster/
- emptyDir: https://kubernetes.io/docs/concepts/storage/volumes/#emptydir
- Content Security Policy: W3C CSP Level 3 https://www.w3.org/TR/CSP3/;
  MDN guide (non-vendor) https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP
- HTTP 429: RFC 6585 section 4 https://www.rfc-editor.org/rfc/rfc6585#section-4

## Open questions (with recommendations)

| Question | Recommendation |
|---|---|
| Run history size | 50 runs in a 64 MiB emptyDir. A run is ~20-40 KB (8 tool results truncated to 2,000 characters, the report, settings); 50 runs ≈ 2 MB. Raise only if the eval needs more in one go (it writes its own results to results/ anyway). |
| Persist runs across restarts | No (emptyDir). The eval's results are committed under results/; Loki keeps the CronJob's logs. A PVC adds backup and airgap work for no MVP need. |
| Auth beyond NetworkPolicy | None for the MVP: one user, access by port-forward gated by RBAC. Revisit (new ADR) with a second user or any exposure beyond port-forward (Ingress), as ADR 0001 says for the endpoint. |
| Trace backend (Week 4) | Keep the run JSON's `tool_calls` as the trace for now; Week 4's ADR picks an OpenTelemetry backend. Recommendation for that ADR: one that runs airgapped and already fits the platform (Grafana Tempo, alongside Loki and Grafana), decided by measurement there. |
| Queue instead of 429 | 429. A queue of synchronous 5-minute requests ties up connections and clients' timeouts; the scorer retries once after `Retry-After`; agentctl exits 3 (busy) and the CronJob counts that as a skipped run. |
| Thinking flag | In the contract now, default off, untested until Week 4. |
