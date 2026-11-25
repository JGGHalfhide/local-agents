# 0009. The status reporter keeps thinking off; opt-in stays available per request

Status: accepted (Week 4, 11/25)

## Context

local-airgap-LLM serves Qwen3.5 4B with thinking off by default (its ADR
0006); a client opts in per request with
`chat_template_kwargs: {"enable_thinking": true}`, and the server caps
thinking at 1024 tokens. There, thinking fixed 3 of 3 multi-step errors
but looped to 8,192 tokens with no answer on 3 of 3 open-ended triage
questions. The roadmap asked for the opt-in to be tested on the status
reporter once it worked with thinking off.

The same 13 fault-injection cases (docs/eval-status.md), run one after the
other on 11/25 with the same image (393577d), prompts and limits
(`config_sha256` b085a9e3, `max_tokens` 1024), greedy, through the operator
API; the only difference is `"thinking": true` in POST /v1/status:

| | Thinking off (results/week4-status-eval/) | Thinking on (results/week4-thinking-status-eval/) |
|---|---|---|
| Faults | 8/8 | 8/8 |
| Controls | 5/5, no findings | 5/5, no findings |
| Ambient findings | 0 | 0 |
| Run errors, ungrounded findings | 0, 0 | 0, 0 |
| Run time | 47.3-93.2 s, median 49.4 s | 132.1-189.6 s, median 149.8 s |
| Model turns (median) | 8 | 9 |

Thinking changed two reports without changing a score: f05 named the
ReplicaSet of the OOM-killed pod instead of the pod; f10 also reported the
pod waiting on the unbound claim as unschedulable (a second view of the
same fault, in the case namespace). No run hit the 300 s deadline.

Every second of a run holds one of the endpoint's 4 slots, shared with
every other client.

## Decision

- The status reporter runs with thinking off: the CronJob, the operators'
  default and the eval. Thinking gave no measured gain on this eval and
  tripled the run time and the slot time.
- The per-request opt-in stays as it is (`agentctl status --thinking`,
  `"thinking": true`): an operator may use it, at about 3x the time.
- No change to local-airgap-LLM: its default (off) and cap (1024) stand.
- Revisit with a harder eval (several faults at once, faults the 4B model
  misses with thinking off): only a case thinking off fails can show a
  gain.
