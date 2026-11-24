# 0001. Endpoint access: NetworkPolicy only, no API key

Status: accepted (Week 1, 11/23)

## Context

Agents call local-airgap-LLM's endpoint at `http://llm-api.llm.svc:8080`.
The question carried over from local-airgap-LLM's roadmap: is NetworkPolicy
enough, or should llama-server also require an API key (from platform-lab's
Ansible Vault)?

What controls access today (read from the manifests and the live cluster,
11/23):

- `llm-api` is an ExternalName Service for the KEDA HTTP add-on's
  interceptor (local-airgap-LLM ADR 0005). The interceptor's NetworkPolicy
  (platform-lab `gitops/keda/networkpolicy-interceptor.yaml`) admits port
  8080 only from pods labelled `inference.local-airgap-llm/client: "true"`
  **in** namespaces with the same label: `namespaceSelector` and
  `podSelector` are in one `from` entry, so both must match.
- llama-server itself (`llm` namespace, default deny in and out) admits only
  the interceptor and Prometheus (local-airgap-LLM
  `deploy/llm/networkpolicy.yaml`), so a client cannot bypass the
  interceptor.
- Tested by local-airgap-LLM's `make smoke` on both clusters: unlabelled
  pod blocked at `llm-api` (timeout), no bypass of the interceptor
  (timeout), no egress from the server (e.g. docs/scans/week4-smoke-test.txt
  there).
- Who can grant access: setting a namespace label needs cluster-wide rights.
  On the build cluster these are held by `system:masters` (the admin
  kubeconfig), RKE2's own Helm jobs, Velero, and Argo CD's application
  controller (`*` on `*`), which applies what is committed to the repos. No
  namespace carries the label today; the smoke test labels its own
  short-lived namespaces.

Options:

- **NetworkPolicy only (today).** Access is a label, granted by a commit
  (Argo CD) or the admin kubeconfig. No Secret to create, distribute, rotate
  or package for the airgap. No change to the endpoint.
- **NetworkPolicy plus an API key** in llama-server (`--api-key`): a second
  check, so a pod that gets the labels still needs the key. Costs: a change
  in local-airgap-LLM (flags, Secret, smoke test, Zarf package); a Secret in
  every client namespace, from Vault, rotated, and carried through the
  airgap flow. A shared key adds no identity per agent; one key per agent
  would, but the server only accepts or rejects, it has no per-key limits
  or per-key logs worth having here.

What a key would protect against, in this lab: a workload that can create
pods in a labelled namespace, or label one, but cannot read that
namespace's Secrets. With one user, everything delivered by GitOps, and
agents that do not create pods (read-only tools, Week 2), that workload
does not exist.

What neither option gives: per-agent identity, quotas or priorities at the
endpoint (4 slots shared by every client). Those are this repo's job
(tracing in Week 4; concurrency in the open questions).

## Decision

NetworkPolicy only (the user's decision, 11/23). No API key; no change to
local-airgap-LLM.

- Each agent's namespace and each agent pod carry
  `inference.local-airgap-llm/client: "true"`, set in this repo's manifests
  (GitOps), never by hand.
- Only agent pods get the label. Tool servers and other components run
  unlabelled (in their own namespace where possible), so a tool cannot call
  the model.
- Agents' and tools' RBAC must not allow creating pods or changing labels in
  a labelled namespace (Week 2). Write actions are a Week 6 decision.
- Every model call is attributed by this repo's tracing (Week 4), not by the
  endpoint.
- The Week 2 smoke test repeats the checks for agents: an unlabelled pod in
  the agent namespace is blocked, a labelled pod in an unlabelled namespace
  is blocked, the agent reaches `llm-api`.

Revisit (new ADR) if any of these changes: a second user or untrusted
workloads on the clusters; a client outside the cluster; an agent or tool
that can create pods or edit labels; a need for per-client limits at the
endpoint.
