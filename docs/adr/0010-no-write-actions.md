# 0010. No write actions: the status reporter stays read-only

Status: accepted (Week 6, 11/25)

## Context

The roadmap asked whether the agent should ever change the cluster (for
example restart a Deployment), and if so how a write would be approved.
Everything so far is read-only by construction:

- RBAC: the `status-reporter` ServiceAccount has get/list/watch only; every
  write, Secrets, pod logs, exec, attach and port-forward are denied
  (measured with `kubectl auth can-i`, docs/scans/week2-identity-smoke.txt).
- Tools: 11 in-process functions, GET requests only (agent/k8s.py); the
  model chooses among them with schema-checked arguments and never sends a
  raw API request (ADR 0007).
- Interface: runs start only through POST /v1/status; the web view has no
  forms (ADR 0005).
- The model reads text the workloads control: event messages (a readiness
  probe's output), object names, Argo CD health messages. Week 6's
  prompt-injection cases plant instructions there
  (docs/eval-status.md); a model that can only read cannot be talked into
  changing anything.

| | Not offered (chosen) | Offered behind approval |
|---|---|---|
| What changes | Nothing: an ADR | A write tool that only proposes, an approval endpoint and `agentctl approve`, a second, narrower Role for the write, tests, eval cases for proposals |
| Blast radius of a wrong or injected answer | A wrong report | A wrong report, or a proposed change an operator may approve under time pressure |
| Value for a status reporter | Its job is the report | An operator can already restart a Deployment with kubectl; the agent saves one command |
| Work | None | About a week, plus its own eval |

The user chose not to offer writes (11/25).

## Decision

- The status reporter has no write actions: no write tool, no write RBAC,
  no approval flow. Its output is a report; any change is made by an
  operator with their own credentials.
- Keep the read-only guarantees testable: the identity smoke test (can-i
  denials) and the prompt-injection cases stay in the eval.
- Revisit only with a concrete need, in a new ADR: a write would then be a
  separate tool with its own ServiceAccount and Role scoped to the one
  verb and resource, proposed by the agent and executed only after an
  operator approves it through the API, never by the model directly.
