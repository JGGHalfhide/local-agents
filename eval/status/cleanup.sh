#!/usr/bin/env bash
# STUB (approved spec, docs/eval-status.md): remove what inject.sh created. Not
# implemented: it lists what it would delete, then exits 3.
#
# Usage: KUBECONFIG=... eval/status/cleanup.sh [<case-id>]   (no id: all cases)
#
# Rules the implementation must keep:
# - Deletes only namespaces whose name starts with agent-eval- AND that carry
#   label local-agents/eval=true (both, so a mislabelled or similarly named
#   namespace is never touched); prints each one before deleting it.
# - Waits until the namespaces are gone, then checks that no object with the
#   label remains; exits non-zero otherwise.
# - Read-only listing works today (below).
set -euo pipefail

case_id=${1:-}
if [[ -n $case_id ]]; then
  [[ $case_id =~ ^[fk][0-9]{2}$ ]] || { echo "bad case id: $case_id" >&2; exit 2; }
  match="^agent-eval-$case_id\$"
else
  match='^agent-eval-'
fi

echo "would delete (label local-agents/eval=true, name $match):"
kubectl get ns -l local-agents/eval=true -o name 2>/dev/null \
  | sed 's#^namespace/##' | grep -E "$match" | sed 's/^/  /' || echo "  (none)"
echo "not implemented yet" >&2
exit 3
