# 0002. Agent runtime: a plain loop on the openai SDK

Status: accepted (Week 1, 11/24)

## Context

The status reporter (ADR 0003) is a tool loop: the model calls read-only
tools, reads their capped output, and ends with a JSON report. The runtime
runs that loop against local-airgap-LLM's endpoint (Qwen3.5 4B, llama-server,
OpenAI-compatible), must be packaged for the airgap and pass the supply
chain, and must keep the client backend-neutral (base URL, model, key from
config).

Candidates, pinned as in [scans/week1-runtime-footprint.txt](../scans/week1-runtime-footprint.txt):
a plain loop on the standard library, a plain loop on the openai SDK 3.46.0,
pydantic-ai 2.66.0, LangGraph 1.2.20 (with langchain-openai 1.7.4), smolagents
1.26.0.

Spike (11/24, [scans/week1-runtime-spike.txt](../scans/week1-runtime-spike.txt),
code in eval/spike/): the same 6 tools, system prompt, report schema and caps
for every candidate (8 tool calls, 3,500 characters per result, 1,024
completion tokens, temperature 0, thinking off), 4 fixtures (a recorded
healthy cluster; a crash loop, an admission denial and a KEDA-at-zero
control constructed from it), one run each, every request logged by a proxy.

| Candidate | Valid reports | Exceptions | Prompt tokens / run (mean) | Median time | Wheels (size) |
|---|---|---|---|---|---|
| plain loop, openai SDK | 4/4 | 0 | 42,900 | 167 s | 14 (6 MiB) |
| plain loop, stdlib | 4/4 | 0 | 42,000 | 221 s | 0 |
| LangGraph | 3/4 | 1 | 31,900 | 290 s | 43 (19 MiB) |
| smolagents | 2/4 | 1 | 83,500 | 278 s | 35 (22 MiB) |
| pydantic-ai | 0/4 | 4 | 4,300 | 176 s | 26 (12 MiB) |

Behaviour of the endpoint that every runtime has to handle (found in the
spike, reproduced by replaying the recorded requests):

- A request ending with an assistant message is rejected when it also asks
  for structured output (`response_format`): "Failed to initialize
  samplers" (400). LangGraph's structured-output step does exactly this;
  adding a user turn fixes it.
- A tool call whose arguments are not JSON, once resent in the history,
  makes the server answer 500 for the whole conversation.
- `tool_choice: "required"` is not enforced: the model sometimes answers
  with text. With `"auto"` and the report requested as text (pydantic-ai's
  `PromptedOutput`), it answered without calling any tool and invented a
  report, 4 of 4.
- A repetition loop (one tool called 340 times) runs until the client
  stops it.
- A report with several faults and evidence can exceed 512 completion
  tokens; 1,024 fit all but one.

What the frameworks add or cost here: pydantic-ai has built-in OpenTelemetry
GenAI instrumentation, but its default (report as a forced tool call) was cut
off at the token cap and its text output skipped the tools. LangGraph needed
its structured-output step replaced and pulls in langsmith (a hosted tracing
client); its transitive pins drifted within a day (langsmith 0.16.1 to
0.16.2). smolagents uses about twice the prompt tokens (its own long prompt,
text-only steps that do not count as tool calls) and one run exceeded 15
minutes. All candidates vendor as binary wheels for Linux x86-64; all keep
base URL, model and key in config.

Answer quality was the same weak level across runtimes (all found the crash
loop; most missed the admission denial; every report listed 4-7 false
faults from boot-time warnings and KEDA scale-to-zero): that comes from the
shared prompt and tool output, not from the runtime.

## Decision

A plain tool loop on the official openai SDK (the user's decision, 11/24).

- About 50 lines (eval/spike/run_openai.py is the starting point). It must
  keep: a cap on model turns (then one final request without tools); tool
  arguments checked, and malformed ones replaced before the history is
  resent; the final structured request ending on a user turn; a per-call
  timeout.
- Pinned: openai and its 13 dependencies, by version and hash (a lock file,
  not top-level pins: transitive versions drift).
- Tracing (Week 4): OpenTelemetry's `opentelemetry-instrumentation-openai-v2`
  (beta) or spans written in the loop; decided then.
- Config: base URL, model and API-key variable from a file; the in-cluster
  endpoint needs no key (ADR 0001).

Revisit (new ADR) if: the agent needs multi-agent orchestration, durable
state or human approval steps that a framework provides; or a framework
version handles this endpoint's behaviour above without workarounds.
