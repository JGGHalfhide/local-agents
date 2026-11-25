# 0007. Tool interface: tools are in-process functions

Status: accepted (Week 2, 11/24)

## Context

The status reporter (ADR 0003) has 11 read-only tools in agent/tools.py
(overview, list_namespaces, list_nodes, list_pods, list_workloads,
list_events, list_keda_objects, list_pvcs, list_argocd_apps, pod_metrics,
get_status). Each is a Python function called by the tool loop (ADR 0002)
with validated arguments; it reads the Kubernetes API with GET requests
only (agent/k8s.py) under the agent's ServiceAccount, and returns compact
rows capped at 3,500 characters.

The roadmap left open whether tools should instead run as separate tool
servers (for example MCP servers), each its own Deployment.

| | In-process functions (today) | Tool servers (e.g. MCP) |
|---|---|---|
| Identity | One ServiceAccount, get/list/watch only (deploy/agents/rbac.yaml); the model can only pick among the 11 GET tools with schema-checked arguments | One ServiceAccount per server; the agent pod could hold no Kubernetes token at all |
| Moving parts | None added | A server image, Deployment, Service, ServiceAccount and NetworkPolicy per server; a protocol client in the loop; another hop on every call |
| Supply chain and airgap | Already in the signed agent image (ADR 0004) and the Week 5 Zarf package | Each server image through `make image`, Kyverno and Zarf as well |
| Reuse | One agent consumes the tools | Pays off when several agents or clients share tools |
| Eval | 8/8 faults, 5/5 controls with in-process tools (results/week2-status-eval/) | Unmeasured |

ADR 0006 limits the project to one agent, so no second consumer exists. The
one real gain of a tool server, separating the Kubernetes token from the
process that talks to the model, is small here: the token is read-only,
denied Secrets, logs, exec and every write (docs/scans/week2-identity-smoke.txt),
and the model never sends raw API requests.

## Decision

Tools stay in-process functions in the agent image; no tool servers and no
MCP. Revisit only if a second agent or client needs the same tools, or if a
tool needs rights the agent itself must not hold (for example a write
action, decided in Week 6).
