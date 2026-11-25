#!/usr/bin/env bash
# Remove what eval/status/inject.sh created.
#
#   KUBECONFIG=... eval/status/cleanup.sh [<case-id>]     (no id: all cases)
#   LIST_ONLY=1 eval/status/cleanup.sh                    (show, delete nothing)
#
# Deletes only namespaces whose name starts with agent-eval- AND that carry
# the label local-agents/eval=true (both, so a similarly named or mislabelled
# namespace is never touched); prints each one before deleting it; waits
# until they are gone. Refuses a kubeconfig that is not the build cluster's
# or the airgapped rehearsal cluster's (11/25, user's OK).
set -euo pipefail

ALLOWED_SERVERS="${ALLOWED_SERVERS:-https://192.168.122.10:6443 https://192.168.122.20:6443}"
case_id=${1:-}
if [[ -n $case_id ]]; then
  [[ $case_id =~ ^[fk][0-9]{2}$ || $case_id =~ ^k[0-9]$ ]] || { echo "bad case id: $case_id" >&2; exit 2; }
  match="^agent-eval-$case_id\$"
else
  match='^agent-eval-'
fi

server="$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')"
[[ " $ALLOWED_SERVERS " == *" $server "* ]] || { echo "refusing: kubeconfig server $server is not an eval cluster ($ALLOWED_SERVERS)" >&2; exit 3; }

mapfile -t targets < <(kubectl get ns -l local-agents/eval=true -o name | sed 's#^namespace/##' | grep -E "$match" || true)
if [[ ${#targets[@]} -eq 0 ]]; then echo "nothing to delete"; exit 0; fi
printf 'deleting namespace %s\n' "${targets[@]}"
[[ "${LIST_ONLY:-0}" == 1 ]] && { echo "LIST_ONLY=1: nothing deleted"; exit 0; }
kubectl delete ns "${targets[@]}" --wait=true --timeout=180s >/dev/null
left="$(kubectl get ns -l local-agents/eval=true -o name | sed 's#^namespace/##' | grep -E "$match" || true)"
[[ -z "$left" ]] || { echo "still present: $left" >&2; exit 1; }
echo "gone"
