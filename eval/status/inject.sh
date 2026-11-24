#!/usr/bin/env bash
# STUB (approved spec, docs/eval-status.md): inject one fault or control for the
# status reporter evaluation. Not implemented: it validates its input and
# prints its plan, then exits 3 without touching the cluster. Manifests go in
# eval/status/cases/<id>/ when implemented; injecting waits for the user's go.
#
# Usage: KUBECONFIG=... eval/status/inject.sh <case-id>   (e.g. f04, k3)
#
# Rules the implementation must keep:
# - Writes only in namespace agent-eval-<case-id>, created here with label
#   local-agents/eval=true; never in a platform namespace.
# - Refuses a kubeconfig whose server is not the build cluster's.
# - Every workload: signed image from 127.0.0.1:30500 by digest (alpine 3.22,
#   podinfo 6.17.0), app.kubernetes.io/name label, requests and limits,
#   restricted securityContext; it breaks only what its case is about.
# - Before injecting: record the ambient snapshot (unhealthy pods, workloads,
#   Applications outside agent-eval-*) to results/<run>/<case>/ambient.json;
#   abort if a platform component is unhealthy.
# - After injecting: wait until the fault is visible through the API (the
#   case's condition, e.g. waiting reason CrashLoopBackOff) or time out.
set -euo pipefail

# Approved by the user 11/24 (docs/eval-status.md, Decisions). f09 dropped.
APPROVED=(f01 f02 f04 f05 f06 f07 f08 f10 k1 k2 k3 k4 k5)
KNOWN=("${APPROVED[@]}")

case_id=${1:-}
[[ -n $case_id ]] || { echo "usage: $0 <case-id>" >&2; exit 2; }
[[ $case_id =~ ^[fk][0-9]{2}$ ]] || { echo "bad case id: $case_id" >&2; exit 2; }
printf '%s\n' "${KNOWN[@]}" | grep -qx "$case_id" || { echo "unknown case: $case_id" >&2; exit 2; }
ns="agent-eval-$case_id"

echo "plan: create namespace $ns (label local-agents/eval=true), record ambient snapshot,"
echo "      apply eval/status/cases/$case_id/*.yaml into $ns, wait until the fault is visible"

if ! printf '%s\n' "${APPROVED[@]}" | grep -qx "$case_id"; then
  echo "refusing: $case_id is not approved (docs/eval-status.md, Decisions)" >&2
  exit 3
fi
echo "not implemented yet" >&2
exit 3
