# Status reporter evaluation: fault injection

Status: **implemented and run** (Week 2, 11/24; approved 11/24). Approved
cases: faults f01, f02, f04, f05, f06, f07, f08, f10; controls k1-k5; the
context caps below. f09 (Argo CD) dropped. All cases stay in `agent-eval-*`
namespaces; a fault outside them needs the user's approval of that specific
fault. Code: eval/status/ (cases.yaml, cases/*.yaml, inject.sh, cleanup.sh,
score.py, run_eval.py); every run goes through the operator API (ADR 0005).

## Thinking on, Week 4 (11/25, results/week4-thinking-status-eval/)

The same 13 cases with `"thinking": true` (run_eval.py --thinking), same
image and config: faults 8/8, controls 5/5, no ambient findings, no errors,
nothing ungrounded; 7-8 tool calls; 132.1-189.6 s, median 149.8 s (3.0x
thinking off); output tokens median 1,299 vs 231, largest single output 842
of the 1024 max_tokens, none cut off (docs/scans/week4-thinking-tokens.txt). Two reports differ without changing a score: f05 named the
ReplicaSet of the OOM-killed pod, f10 added the pod waiting on the unbound
claim. Decision: thinking stays off for the status reporter
([ADR 0009](adr/0009-status-reporter-thinking-off.md)).

## Results, Week 4 (11/25, results/week4-status-eval/)

Faults 8/8, controls 5/5 reported healthy with no findings, **no ambient
findings in any of the 13 runs**; every run grounded, 6-8 tool calls,
47.3-93.2 s, median 49.4 s (Week 3: 48.9 s). Agent image 393577d, first
pass, one greedy run per case. Same rendered system prompt as Week 3
(`prompt_sha256` 3b79b738...), now read from deploy/agents/prompts/:
every run records `config_sha256` b085a9e3... (prompts and limits), which
the CI check eval/status/check_config.py requires.

Changes since Week 3:
- Tracing (ADR 0008): every run has a `trace_id` in Tempo.
- Prompts and limits are files synced by Argo CD (agent/profile.py).
- A controller's `FailedCreate` followed by a later `SuccessfulCreate` on
  the same object is resolved (a CronJob's Jobs rejected while Kyverno and
  Zot started after a VM boot were a false fault in the first traced run,
  docs/scans/week4-tracing.txt). f06 (no later success) still found.

From the traces (Tempo, per model call): the final structured request
takes 35-45 s in every run, 40-70% of it. The slowest runs (f05 93.2 s,
f06 84.7 s, f08 78.3 s) made one tool call per turn: 8-9 model calls and
22-27k input tokens, against 3 calls and 7k tokens for k4 (48.9 s), where
the model asked for several tools per turn.

## Results, Week 3 (11/24, results/week3-status-eval/)

Faults 8/8 found, located and classified; controls 5/5 reported healthy
with no findings at all; **no ambient findings in any of the 13 runs**
(Week 2: 1-5 per run). f06 and f08 now scored strictly (the finding must
name the blocked object in the case namespace; Week 2 accepted the case
namespace anywhere in the finding). Every run grounded, 6-8 tool calls,
39.6-84.4 s, median 48.9 s (Week 2: 56-128 s). Agent image f906bd3. One
greedy run per case.

Changes since Week 2 (the Week 2 follow-ups):
- The hourly CronJob treats 429 as a skipped run (agentctl exit 3), not a
  failed Job; a failed Job from Week 2's 429 was every later run's ambient
  finding. Seen live: the 03:00 run during the eval completed in 3 s.
- Conditions where False is healthy (Suspended, Failed, FailureTarget,
  ReplicaFailure) are reported only when True (a completed Job's
  `Suspended=False(JobResumed)` was printed as bad).
- Kyverno PolicyViolation events are located at the object named in the
  message (Kyverno files them under the policy in `default`), marked
  "blocked at admission by <policy>"; hidden once that namespace is gone.

Passes on the way, kept:
- first-pass/ (image c4f5677): faults 7/8, controls 5/5. f06 located but
  classified `image-pull`: with the policy no longer the event's object,
  the message "failed to evaluate policy: GET .../manifests/sha256:..."
  read as a pull error. Fix: the row says "blocked at admission by
  <policy>" (f906bd3).
- rerun-f906bd3/ (f06, f08 only): f08 passed, f06 not reported at all. The
  leftover failed Job from Week 2 (a 429) was still in `agents`; the model
  spent its calls on it and merged the two into one story about the agent's
  own namespace. The Job was deleted (the user's OK; its only log line, the
  429, is quoted above) and the full set rerun: the result above.
- Lesson: one unrelated real fault in the cluster can pull a 4B model off
  the injected one; the eval assumes an otherwise healthy cluster.

## Results, Week 2 (11/24, results/week2-status-eval/)

Faults 8/8 found, located and classified; controls 5/5 with nothing
reported in their namespace; every run grounded, 7-8 valid tool calls,
56-128 s. One greedy run per case (no variance study).

- First pass (results/week2-status-eval/first-pass/): faults 6/6, controls
  3/4. f06 and f08 could not be injected as specified (below); k1's
  visibility check misread zero replicas; k2 failed tool validity (the model
  asked get_status for a CronJob, which the tool did not accept). Fixed
  (agent image e6ae522, eval scripts) and those four cases rerun.
- f06 and f08 as run: Kyverno rejects the Deployment and the DaemonSet
  themselves at admission (autogen applies the pod rules to workloads;
  platform-lab supply-chain.md says so for unsigned images). Nothing is
  created; the fault is visible only as Kyverno's PolicyViolation event,
  filed under the policy in namespace `default`. They are scored as located
  when the case namespace appears in the finding's namespace, object or
  evidence. The rerun's events overlapped the first pass's (events live
  about an hour). A DaemonSet that exists with 0 pods (the c14 symptom)
  cannot be produced in an ordinary namespace under these policies.
- Ambient findings (outside agent-eval-*, not scored) in most runs: the
  earlier unsigned-image admission test, the CronJob's warning about Jobs
  created by hand, the hourly Job that got 429 while an eval run held the
  API, and twice a healthy kube-system object (a completed Job whose
  JobResumed=False condition is printed). Follow-ups in ROADMAP.md.

Agent 1, the read-only status reporter (ADR 0003), is scored automatically:
a known fault is created in a disposable namespace, the agent reports on
the cluster, and its report is compared with what was injected. The
triage evaluation set (eval.md) stays agent 2's measure.

## Facts this spec depends on (build cluster, 11/24)

| Fact | How checked |
|---|---|
| Per-slot context is 32768 tokens from **one unified KV pool** shared by the 4 slots (`--parallel` unset = auto, so `--kv-unified` is on by default); no slot is guaranteed more than what the other three leave | `/props`, `/slots` via the interceptor: [scans/week1-llm-slots.txt](scans/week1-llm-slots.txt) |
| Pods in any namespace but `kube-system` must pass Kyverno: images from `127.0.0.1:30500` (or `127.0.0.1:31999`), pinned by digest; images from 30500 signed with the lab key; `app.kubernetes.io/name` label; CPU/memory requests and limits; restricted security context; no hostPath, privileged, latest tag or Secret env | `kubectl get validatingpolicies,imagevalidatingpolicies`; platform-lab `gitops/policies/` |
| Cluster default Pod Security is the RKE2 CIS profile's (`--admission-control-config-file=/etc/rancher/rke2/rke2-pss.yaml`, restricted, as c14 records); an unlabelled `agent-eval-*` namespace gets it | kube-apiserver args; namespace labels |
| Zot allows anonymous reads | platform-lab `gitops/apps/zot.yaml` (`anonymousPolicy: ["read"]`) |
| Signed images in Zot usable for fault workloads: `library/alpine:3.22@sha256:49340b34…898f`, `stefanprodan/podinfo:6.17.0@sha256:fa2f27c1…efb0` (`.sig` and `.att` tags present) | Zot `/v2/<repo>/tags/list` from the node |
| `verify-platform-images` checks only `127.0.0.1:30500/*`; nothing listens on `127.0.0.1:31999` on the build cluster (connection refused) | policy file; `curl` from the node |
| Argo CD Applications exist only in `argocd` (`application.namespaces` unset), so an Argo CD fault would touch a platform namespace (f09, dropped) | `argocd-cmd-params-cm`; `kubectl get applications -A` |
| One StorageClass, `local-path` (default, `WaitForFirstConsumer`) | `kubectl get sc` |
| metrics.k8s.io is served (rke2-metrics-server) | `kubectl get apiservices` |
| A model call wakes llama-server: during any agent run `llm/llama-server` is at 1 replica, not 0 | KEDA HTTP add-on design; seen on 11/24 (`/props` woke it) |

## Cases

Each case runs alone, in its own namespace `agent-eval-<id>` (labelled
`local-agents/eval: "true"`), created by `eval/status/inject.sh` and
deleted by `eval/status/cleanup.sh`. Every workload uses the signed images
above and passes every policy except the one a case is about.

### Faults

| Id | Fault | How it is made | Observable through the API? | Category | Objects accepted as "located" |
|---|---|---|---|---|---|
| f01 | Deployment at 0 replicas, not KEDA/HPA managed | podinfo Deployment `replicas: 0` **plus a Service selecting it** | Yes (spec.replicas 0, no ScaledObject, Service has no endpoints). Without the Service, 0 replicas is a legitimate state, not a fault. Needs `services` and `endpointslices` read | `scaled-to-zero` | Deployment, Service |
| f02 | ImagePullBackOff | alpine by digest from `127.0.0.1:31999/…` (allowed, not verified, nothing listening) | Yes (waiting reason `ErrImagePull`/`ImagePullBackOff`, kubelet event "connection refused"). **Not c05**: a digest missing from Zot is denied at admission by `verify-platform-images` (it becomes f06). Uses a policy gap platform-lab plans to close; then this case becomes an admission denial | `image-pull` | Pod, owning ReplicaSet/Deployment |
| ~~f03~~ | Missing imagePullSecret (c04) | — | **No, not a fault here**: Zot reads are anonymous, so the pod runs; the kubelet only logs a warning event. c04 needs the airgap cluster's authenticated Zarf registry. Proposed instead as control k5 | — | — |
| f04 | CrashLoopBackOff from bad args (c03) | alpine with `command: ["/bin/sh","-c"]`, `args: ["exec /bin/no-such-binary"]` | Yes (waiting reason `CrashLoopBackOff`, lastState exit code 127, restarts) | `crash-loop` | Pod, owner chain |
| f05 | OOMKilled restart (c01) | alpine `tail /dev/zero`, memory limit 32Mi | Yes (lastState.terminated.reason `OOMKilled`, restarts) | `oom-killed` | Pod, owner chain |
| f06 | Admission denial by Kyverno (c06) | Deployment whose pod template uses `127.0.0.1:30500/library/alpine@sha256:<digest not in Zot>` | Yes: the Deployment is admitted; its ReplicaSet gets `FailedCreate` events with the policy message, condition `ReplicaFailure`, 0 pods | `admission-denied` | Deployment, ReplicaSet |
| f07 | Unschedulable Pending pod | alpine requesting `cpu: "64"` | Yes (`FailedScheduling`, PodScheduled=False). Consumes nothing | `unschedulable` | Pod, owner chain |
| f08 | DaemonSet with 0 pods, Pod Security rejection (c14 symptom) | DaemonSet with `hostNetwork: true` in a restricted namespace | Yes (desired 1, current 0, `FailedCreate` events). Both Pod Security and Kyverno `pod-security-restricted` deny; which message appears is not yet checked. Tests the symptom only: c14's cause (Zarf resetting labels) cannot be injected in a fresh namespace. Nothing runs with host access | `admission-denied` | DaemonSet |
| ~~f09~~ | Argo CD app Degraded / OutOfSync | — | Dropped (11/24): would need an Application in `argocd`, a platform namespace. The agent still reads Applications, so a real one going unhealthy is reported | — | — |
| f10 | Unbound PVC | PVC with `storageClassName: agent-eval-missing` + a pod using it | Yes (PVC Pending, pod Pending, event about the unknown class). A `local-path` PVC with no consumer is also Pending, by design (`WaitForFirstConsumer`): not used as a fault | `storage-unbound` | PVC, Pod |

### Healthy controls (the agent must report no fault in them)

| Id | Control | How | Observable? |
|---|---|---|---|
| k1 | KEDA-managed workload at zero (c08) | **Changed from the prompt**: `llm/llama-server` cannot be seen at zero during a run, because the agent's own model calls wake it. Instead: podinfo Deployment + a KEDA `ScaledObject` (`minReplicaCount: 0`, a cron trigger whose window never opens) in `agent-eval-k1` | Yes (0 replicas, ScaledObject Ready, not Active). Isolated; no platform change |
| k2 | Memory near the limit, no OOM (c02) | alpine holding ~80% of a 64Mi limit, restarts 0 | Yes, through `pod_metrics` (`metrics.k8s.io` pods read) |
| k3 | Completed Job pod | Job running `true` | Yes (Job Complete, pod Succeeded) |
| k4 | Fully healthy namespace | podinfo Deployment 1/1 + Service | Yes |
| k5 | Warning event, workload healthy (from c04) | Pod referencing an absent imagePullSecret; Zot serves it anonymously, pod Running | Yes (warning event only). Tests that a warning is not reported as a fault |

### Categories (closed set)

`scaled-to-zero`, `image-pull`, `crash-loop`, `oom-killed`,
`admission-denied`, `unschedulable`, `storage-unbound`, `gitops-unhealthy`,
`node-not-ready`, `other`. (`node-not-ready` is in the set so the agent has
a place for it; no case injects it.) Admission denials by Kyverno and by Pod
Security share one category, since f08 may carry either message.
`gitops-unhealthy` stays in the set (the agent reads Applications) although
no case injects it since f09 was dropped.

## Agent output (JSON schema, enforced by the endpoint)

```json
{"faults": [{"namespace": "...", "kind": "...", "name": "...",
             "category": "<one of the set>", "evidence": ["..."]}],
 "summary": "..."}
```

An empty `faults` list means "no fault".

## Scoring (automatic)

The run's scope is the whole cluster. Before each run the injector records
an **ambient snapshot**: anything already unhealthy outside `agent-eval-*`
(the run is skipped if a platform component is unhealthy, so ambient
faults do not hide in the scores).

Per fault case, all must hold to pass:

| Check | Passes when |
|---|---|
| **detect** | `faults` is non-empty |
| **locate** | a reported fault has the case's namespace and one of its accepted (kind, name) pairs |
| **classify** | that fault's category is the expected one |
| **no false positives** | no other fault is reported in `agent-eval-*`, and none outside it unless in the ambient snapshot |
| **grounding** | every namespace and object name in the report appears verbatim in at least one tool result of the run |
| **tool validity** | every call names a known tool with schema-valid arguments; no forbidden kind (e.g. Secret); call count ≤ the cap (below) |

A control passes when no fault is reported in its namespace, plus the
false-positive, grounding and tool-validity checks.

Reported per configuration: pass rate over faults and over controls, each
check separately, tool calls, input and output tokens, latency per run.

### Run-to-run variance

- Greedy (temperature 0): every case run twice; report whether the tool-call
  sequence and the report match. llama.cpp with batching is not guaranteed
  bit-exact, so this is measured, not assumed.
- Any sampled configuration: every case 3 times; report passes per case
  (0-3) and the mean. (Week 1's sampled configurations ran once.)
- Runs are sequential (one agent run at a time on the 4 slots).

## Tools and identity (v1)

### Tools

Each returns compact rows, not raw objects: only status fields that tell
health (phase, ready, restarts, waiting/terminated reason, conditions not
True, desired vs ready counts). Pod specs are never returned (they can
carry env values); Secret names in `imagePullSecrets` are not either.

| Tool | Returns |
|---|---|
| `overview(namespace?)` | added 11/24: everything not healthy now (nodes, pods, workloads, warning events, PVCs, Argo CD apps) in one result, plus healthy counts; the model starts here |
| `list_namespaces()` | name, phase |
| `list_pods(namespace?)` | pod, phase, ready, restarts, waiting reason, last terminated reason/exit code, node |
| `list_workloads(namespace?)` | Deployments, StatefulSets, DaemonSets, ReplicaSets with failures, Jobs: desired / ready / available, conditions not True |
| `list_events(namespace?, type="Warning")` | newest first, deduplicated by (object, reason), count, message cut to 200 chars |
| `get_status(kind, namespace, name)` | conditions and status of one object; `kind` from the allowlist below only |
| `list_pvcs(namespace?)` | phase, storage class, capacity |
| `list_nodes()` | ready, pressure conditions, allocatable vs requested |
| `list_argocd_apps()` | name, sync, health, message |
| `list_keda_objects(namespace?)` | ScaledObjects / HTTPScaledObjects: target, min/max, Ready, Active, Paused |
| `pod_metrics(namespace)` | memory and CPU usage vs limit per container (k2) |
| `list_pvcs(namespace?)`, `list_argocd_apps()` | added 11/24: PVC phase, storage class and whether it exists (f10); Application sync and health |

### ServiceAccount and ClusterRole

`agent-status-reporter` in the agent's namespace; one ClusterRole,
`get`, `list`, `watch` only:

| API group | Resources |
|---|---|
| `""` | pods, events, namespaces, nodes, persistentvolumeclaims, services (f01) |
| `discovery.k8s.io` | endpointslices (f01) |
| `events.k8s.io` | events |
| `apps` | deployments, replicasets, statefulsets, daemonsets |
| `batch` | jobs, cronjobs |
| `argoproj.io` | applications |
| `keda.sh` | scaledobjects, scaledjobs |
| `http.keda.sh` | httpscaledobjects |
| `storage.k8s.io` | storageclasses (f10) |
| `metrics.k8s.io` | pods (k2) |

No Secrets, no `pods/exec`, no `pods/log`, no TriggerAuthentications, no
create/update/delete/patch anywhere. Note: RBAC cannot hide fields, so the
agent's token can read full pod specs (including literal env values); the
tool layer drops them. The smoke test checks with
`kubectl auth can-i --as=system:serviceaccount:<ns>:agent-status-reporter`
that secrets, pods/exec, pods/log and every write are denied.

### Pod logs later (proposal, not v1)

A separate `pod_logs(namespace, pod, previous=false)` tool: last 50 lines or
2 KB, whichever is smaller; redaction of secret-shaped strings (PEM blocks,
`Authorization:` headers, `password=`/`token=` values, long base64 runs)
before the text reaches the model; output wrapped as untrusted data (log
lines are where Week 6's prompt-injection cases go). RBAC: `pods/log` `get`
through a **Role and RoleBinding per allowed namespace**, not the
ClusterRole, starting with `agent-eval-*`, so logs of platform components
stay unreadable until a namespace is added by commit.

## Context budget (approved 11/24)

At ~110 tok/s prompt processing, 1,000 tokens of new input cost about 9 s.
The 32k pool is shared by all 4 slots, so one run must leave room for
another.

| Item | Cap |
|---|---|
| One tool result | 1,000 tokens (about 3,500 characters); longer results truncated with "N more rows omitted" and a hint to narrow by namespace |
| Tool calls per run | 8 |
| System prompt + tool schemas | measured in the ADR 0002 spike; target ≤ 1,500 tokens |
| **Input per run** | **≤ 12,000 tokens** (prompt + all tool results + the model's own turns), so two runs fit in the pool together; the run stops and reports what it has when it would cross the cap |
| Completion per turn | 512 tokens (thinking off) |

Worst case with no prefix reuse: ~12,000 / 110 ≈ 110 s of prompt
processing per run. With llama-server reusing a conversation's prefix
within its slot, each turn only processes its new tokens; how much that
saves is measured in the ADR 0002 spike, from the `usage` fields and
`timings` of each response.

## Client configuration

Backend-neutral: `base_url`, `model`, and `api_key_env` (the name of an
environment variable, empty for the lab endpoint) come from a config file.
In-cluster the base URL is `http://llm-api.llm.svc:8080` and access stays
NetworkPolicy-only (ADR 0001). Running against a hosted model later means a
new config file and no code change; no such run is planned now.

## Cost of a full run (estimate, to be replaced by measurement)

13 cases (f01, f02, f04-f08, f10, k1-k5). At an
estimated 60-120 s per agent run plus about 30 s inject/settle/cleanup:
greedy x2 ≈ 30-55 min; one sampled configuration x3 ≈ 45-80 min. Run
detached (CLAUDE.md), logs in build/.

## Decisions (user, 11/24)

1. Approved: f02, f04, f05, f06, f07, f08, f10; k1, k3, k4.
2. f01 kept, with the "Service has no endpoints" rule (services and endpointslices read).
3. f09 dropped.
4. k2 kept, with the `pod_metrics` tool (metrics.k8s.io pods read).
5. k5 kept.
6. Context caps as above.
