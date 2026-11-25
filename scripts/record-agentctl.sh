#!/usr/bin/env bash
# The agentctl walk-through recorded in docs/media/agentctl.cast (asciinema)
# and docs/media/agentctl.gif (agg): health, a live status run, the run list,
# and the tool-call trace of that run. Needs a port-forward to the API:
#
#   kubectl -n agents port-forward svc/status-reporter 8080:8080 &
#   asciinema rec --idle-time-limit 2 --window-size 120x34 \
#     -c scripts/record-agentctl.sh docs/media/agentctl.cast
#   agg --cols 120 --rows 34 --font-size 14 docs/media/agentctl.cast docs/media/agentctl.gif
#
# Each command is shown as typed, then run against AGENTCTL_ENDPOINT.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export AGENTCTL_ENDPOINT="${AGENTCTL_ENDPOINT:-http://127.0.0.1:8080}"
agentctl() { python3 "$ROOT/agent/agentctl.py" --endpoint "$AGENTCTL_ENDPOINT" "$@"; }

show() {
  printf '\033[1;32m$\033[0m '
  local s="$*" i
  for ((i = 0; i < ${#s}; i++)); do printf '%s' "${s:i:1}"; sleep 0.03; done
  printf '\n'
}

show "agentctl health"
agentctl health
sleep 1

show "agentctl status        # one live run: read-only tools + the local model"
agentctl status
echo "(exit code $?: 0 healthy, 1 fault, 2 error or unknown, 3 busy)"
sleep 1

show "agentctl runs"
agentctl runs | head -8
sleep 1

run_id="$(agentctl --json runs | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["run_id"])')"
show "agentctl trace $run_id"
agentctl trace "$run_id" | head -20
sleep 2
