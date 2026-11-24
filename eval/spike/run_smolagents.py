"""ADR 0002 candidate: smolagents ToolCallingAgent (native tool calls)."""
import argparse
import time

from smolagents import OpenAIServerModel, ToolCallingAgent, tool
from smolagents.monitoring import LogLevel

import common
from report_model import capped


def run(cfg, fixture):
    base, model, key = common.load_config(cfg)
    fx = common.Fixture(fixture)
    llm = OpenAIServerModel(model_id=model, api_base=base, api_key=key,
                            temperature=0, max_tokens=common.MAX_TOKENS)
    agent = ToolCallingAgent(tools=[tool(f) for f in capped(fx)], model=llm,
                             # 2x the tool-call cap: the endpoint does not enforce
                             # tool_choice "required", so some steps are text only
                             # and used up the budget (round 1, 11/24).
                             instructions=common.SYSTEM_PROMPT, max_steps=2 * common.MAX_TOOL_CALLS,
                             verbosity_level=LogLevel.OFF)
    answer = agent.run(common.USER_PROMPT)
    report, errs = common.load_report(answer)
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
