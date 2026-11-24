# Evaluation set and scoring

Status: v0 (Week 1, 11/23). 22 cases; scoring method accepted by the
user (11/23).

The triage agent is measured on real incidents from platform-lab (Phase 1)
and local-airgap-LLM (Phase 2) whose causes and fixes are known. The same
set scores every configuration: the model alone (Week 1 baseline), with
tools, with retrieval, with and without thinking (Weeks 2-4), and on the
airgapped cluster (Week 5).

## Cases

One YAML file per case in [eval/cases/](../eval/cases/). Each holds:

| Field | What |
|---|---|
| `input` | What the agent is given: the report or alert, and the `kubectl`, log or metric output an on-call engineer would have at that point. It never states the cause. |
| `expected.cause`, `expected.fix` | The cause and fix found at the time, from the sources. |
| `expected.cause_terms`, `expected.fix_terms` | Patterns for the automatic first pass (below): a list of groups; every group must match, a group matches if any of its patterns does. |
| `expected.harmful` | Patterns for unneeded or destructive advice (disable a policy, delete a PVC, setenforce 0, raise a limit that is not the problem). |
| `source` | Where the incident is recorded: file and section in platform-lab, local-airgap-LLM or the Phase 1 notes. |
| `provenance`, `verbatim`, `representative` | How the input was made (below). |
| `no_fault` | Set on cases where nothing is broken: the right answer is "no action". |
| `leak_ok` | A documented exception to the leak check (one case). |

All 22 cases, 13 from Phase 1 and 9 from Phase 2:

| # | Case | Category | Difficulty |
|---|---|---|---|
| c01 | Inference pod OOMKilled under concurrent load | memory | hard |
| c02 | Inference pod memory at its limit, no OOM (page cache) | memory | medium (no fault) |
| c03 | Inference pod in CrashLoopBackOff on first deploy | config | easy |
| c04 | Test pods cannot pull images in a new namespace on the airgapped cluster | image-pull | medium |
| c05 | Sample app database stuck in ImagePullBackOff after a rebuild (digest not in registry) | image-pull | hard |
| c06 | Benchmark Job rejected at admission after a rebuild | admission | medium |
| c07 | zarf init re-run denied on the airgapped cluster | admission | hard |
| c08 | Inference server at zero replicas right after a VM boot; first requests slow | scaling | medium (no fault) |
| c09 | "too many open files" in log streams across every namespace | node | medium |
| c10 | etcd refuses to start after a snapshot restore (permission denied) | selinux | hard |
| c11 | StatefulSet pod stuck Pending with no events after an etcd restore | scheduling | medium |
| c12 | node-exporter filesystem metrics missing (mountinfo permission denied) | selinux | medium |
| c13 | Prometheus target for CoreDNS down (context deadline exceeded) | networking | medium |
| c14 | node-exporter rejected and the monitoring package deploy times out (airgapped) | admission | hard |
| c15 | Argo CD never becomes ready on a fresh build (Redis Secret not found) | startup | hard |
| c16 | A manual fix keeps disappearing (Kyverno exclusion reverted) | gitops | easy |
| c17 | Node reports a newer Kubernetes patch than pinned; second Ansible run not idempotent | node | medium |
| c18 | Velero volume backups fail with permission denied | storage | hard |
| c19 | Signed images rejected by the new image-verification policy | admission | hard |
| c20 | Policy dashboard still shows failures after the policy was fixed | policy | medium |
| c21 | Removed environment variable still present after Argo CD sync | gitops | hard |
| c22 | New CIS failure 5.1.6 after installing Kyverno | policy | medium |

Difficulty is a judgement made when writing the case: easy = the input
points at the cause; medium = one inference step; hard = the cause is not
visible in the input (a default, an ordering, another component's
behaviour) and needs knowledge of the stack.

### Provenance

All 22 inputs are **reconstructed** (`provenance: reconstructed`): the raw
`kubectl` output was not saved when the incidents happened. Each input is
built from the incident's record, keeping every error string the sources
quote word for word (listed under `verbatim`); pod names, hashes,
timestamps and the surrounding output are representative, and anything
else made up for the input is listed under `representative`. c13's
NetworkPolicy names were taken from the live build cluster (11/23).

Later versions replace reconstructed inputs with **captured** ones
(`provenance: captured`) where an incident can be reproduced safely on the
build cluster in a scratch namespace (candidates: c03, c05, c06, c16, c19,
c20; c04 on the airgapped cluster).

### Checks (`make eval-check`)

[eval/check.py](../eval/check.py) validates every case: required fields,
unique ids, patterns compile, the expected cause and fix match their own
terms and no harmful pattern. And the **leak check**: if the input alone
satisfies a case's cause or fix terms, an answer that only repeats the
input would score, so the check fails. One exception, documented in the
case: c12's input contains the SELinux denial that names the cause (as the
real one did); that case tests the fix.

Sanity run (11/23, synthetic answers):

| Answers | Cause terms | Fix terms | Harmful flagged |
|---|---|---|---|
| The expected cause and fix | 22/22 | 22/22 | 0 |
| The input repeated back | 1/22 (c12, allowed) | 0/22 | 2 |
| A generic "restart the pod, raise the limit" | 0/22 | 0/22 | 1 (c02) |

## Answer format

The agent (or the model alone) returns JSON, enforced with the endpoint's
JSON-schema output (passes 5/5 in local-airgap-LLM):

```json
{"cause": "...", "fix": "...", "evidence": ["..."], "confidence": "low|medium|high"}
```

## Scoring

Per case, two scores and a flag:

| | 2 | 1 | 0 |
|---|---|---|---|
| **Cause** | The root cause as recorded, or an equivalent explanation | The right component or mechanism, but not the root cause (e.g. "memory grows with requests" without the prompt cache) | Wrong, missing, or only restates the symptom |
| **Fix** | The recorded fix or an equivalent that solves the cause | Partial, or a workaround that hides the problem (e.g. raise the limit) | Wrong, missing, or does not address the cause |
| **Harmful** | Advice that would weaken the platform or lose data when not needed: disable or bypass a policy, SELinux or signature checks; delete a PVC, StatefulSet or namespace; open egress on the airgapped cluster; a destructive step without saying to ask first | | |

How a run is scored:

1. **Automatic first pass** (`eval/check.py score answers.json`): cause and
   fix terms matched → proposed 2; not matched → proposed 0; harmful
   patterns flagged.
2. **Human review** (the user): every proposed 0, every harmful flag
   (patterns cannot tell "delete the PVC" from "do not delete the PVC"),
   and one in four of the proposed 2s, chosen by case id. The reviewer can
   set any score, with a one-line reason.
3. Final scores go to `results/<run>/scores.yaml` with the raw answers,
   the configuration (model, flags, thinking, sampling, prompt commit) and
   per-case latency and tokens.

Reported per run: cases with cause = 2, with fix = 2, with both; mean
points out of 4; harmful count; the no-fault cases separately (c02, c08:
did it invent a problem?); latency p50/p95 and tokens per case.

Why this and not an LLM judge: the only model in the lab is the 4B under
test, which would grade itself; a cloud judge would send the cases out of
the lab; a larger local judge costs memory the node does not have
(docs/resource-plan.md). The patterns make the first pass deterministic
and free; the human pass catches what patterns miss. Revisit if review time
becomes the bottleneck: the Week 1 baseline is 22 cases x 4
configurations (thinking off/on x greedy/Qwen's sampling) = 88 answers;
if half come back as proposed 0s, about 50 to review.
