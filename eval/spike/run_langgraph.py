"""ADR 0002 candidate: LangGraph prebuilt ReAct agent with structured output."""
import argparse
import time

from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

import common
from report_model import Report, capped


def run(cfg, fixture):
    base, model, key = common.load_config(cfg)
    fx = common.Fixture(fixture)
    llm = ChatOpenAI(model=model, base_url=base, api_key=key, temperature=0,
                     max_tokens=common.MAX_TOKENS, max_retries=0, timeout=600)
    tools = [StructuredTool.from_function(f) for f in capped(fx)]
    # No response_format: LangGraph's structured-output step resends the
    # history ending on the agent's own answer, and this llama-server build
    # rejects response_format on a request ending with an assistant message
    # ("Failed to initialize samplers", round 1, 11/24). Parse the answer;
    # if it is not a report, one structured request ending on a user turn.
    agent = create_react_agent(llm, tools, prompt=common.SYSTEM_PROMPT)
    out = agent.invoke({"messages": [("user", common.USER_PROMPT)]},
                       config={"recursion_limit": 2 * common.MAX_TOOL_CALLS + 4})
    report, errs = common.load_report(out["messages"][-1].content)
    if report is None:
        structured = llm.with_structured_output(Report, method="json_schema")
        sr = structured.invoke([("system", common.SYSTEM_PROMPT), *out["messages"], ("user", common.FINAL_ASK)])
        report, errs = common.load_report(sr.model_dump())
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
