"""ADR 0002 candidate: pydantic-ai Agent with structured output."""
import argparse
import time

from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

import common
from report_model import Report, capped


def run(cfg, fixture):
    base, model, key = common.load_config(cfg)
    fx = common.Fixture(fixture)
    agent = Agent(OpenAIChatModel(model, provider=OpenAIProvider(base_url=base, api_key=key)),
                  # Report as text (schema in the prompt), not the default
                  # final_result tool call: with tool_choice "required" the
                  # model wrote prose plus a tool call and hit the 512-token cap
                  # (round 1, 11/24). template=False: no second system message
                  # with the schema (Qwen's template allows a system message
                  # only first: 500 in the rerun); the shared system prompt
                  # already states the JSON report format.
                  output_type=PromptedOutput(Report, template=False), system_prompt=common.SYSTEM_PROMPT, tools=capped(fx),
                  model_settings={"temperature": 0, "max_tokens": common.MAX_TOKENS})
    res = agent.run_sync(common.USER_PROMPT, usage_limits=UsageLimits(request_limit=common.MAX_TOOL_CALLS + 4))
    report, errs = common.load_report(res.output.model_dump())
    return report, errs, fx.calls


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--fixture", required=True)
    a = ap.parse_args()
    t = time.time()
    try:
        report, errs, calls = run(a.config, a.fixture)
        common.result_line(report=report, errors=errs, calls=calls, seconds=round(time.time() - t, 2), exception=None)
    except Exception as e:
        common.result_line(report=None, errors=[], calls=[], seconds=round(time.time() - t, 2), exception=repr(e))
