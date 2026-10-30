"""make_plan against a scripted fake model. Real: the MCP subprocess and the match overview. Fake: the model."""
import asyncio

import pytest

from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.planner import make_plan
from tests.fakes import FakeLLM, reply, tool_use

MATCH = 9041878637
QUESTION = "What were the key mistakes?"


def hyp(id, statement="Radiant lost the 10:41 fight."):
    return {"id": id, "statement": statement, "rationale": "The overview shows a 5-0 fight."}


GOOD_PLAN = {"hypotheses": [hyp("H1"), hyp("H2", "Dragon Knight died too often.")]}
DUPLICATE_IDS_PLAN = {"hypotheses": [hyp("H1"), hyp("H1", "Dragon Knight died too often.")]}


def run(llm, match_id=MATCH, **kwargs):
    async def go():
        async with McpTools() as tools:
            return await make_plan(QUESTION, match_id, tools, llm_call=llm, **kwargs)
    return asyncio.run(go())


def test_valid_plan_is_returned():
    llm = FakeLLM([reply(tool_use("submit_plan", GOOD_PLAN))])
    plan = run(llm)

    assert [h.id for h in plan.hypotheses] == ["H1", "H2"]
    first_call = llm.calls[0]
    assert "WINNER: Dire" in first_call["messages"][0]["content"]       # the real overview was sent
    assert QUESTION in first_call["system"]                              # the planner prompt came from the server
    assert [t["name"] for t in first_call["tools"]] == ["submit_plan"]   # the planner has no investigation tools


def test_duplicate_ids_are_sent_back_and_fixed():
    llm = FakeLLM([reply(tool_use("submit_plan", DUPLICATE_IDS_PLAN)),
                   reply(tool_use("submit_plan", GOOD_PLAN))])
    plan = run(llm)

    assert len(plan.hypotheses) == 2
    feedback = llm.calls[1]["messages"][-1]["content"][0]
    assert feedback["is_error"] is True
    assert "repeated: H1" in feedback["content"]


def test_two_invalid_plans_raise():
    llm = FakeLLM([reply(tool_use("submit_plan", DUPLICATE_IDS_PLAN)),
                   reply(tool_use("submit_plan", DUPLICATE_IDS_PLAN))])
    with pytest.raises(RuntimeError, match="2 attempts"):
        run(llm)
    assert len(llm.calls) == 2                       # exactly two attempts, no third call


def test_a_reply_without_submit_plan_fails_loudly():
    llm = FakeLLM([reply({"type": "text", "text": "I would look at the fights."}, stop_reason="end_turn")])
    with pytest.raises(RuntimeError, match="did not call submit_plan"):
        run(llm)


def test_unfetchable_match_raises_with_the_tool_message(monkeypatch):
    # An id that is not a number fails argument validation in the server, offline.
    llm = FakeLLM([])
    with pytest.raises(RuntimeError, match="Could not fetch match"):
        run(llm, match_id="abc")
    assert llm.calls == []                           # the model was never asked


def test_already_tested_hypotheses_reach_the_prompt():
    llm = FakeLLM([reply(tool_use("submit_plan", GOOD_PLAN))])
    run(llm, avoid=["Dragon Knight died too often.", "Radiant lost the 10:41 fight."])

    system = llm.calls[0]["system"]
    assert "Already tested" in system
    assert "Dragon Knight died too often.\nRadiant lost the 10:41 fight." in system


def test_first_round_prompt_has_no_already_tested_block():
    llm = FakeLLM([reply(tool_use("submit_plan", GOOD_PLAN))])
    run(llm)
    assert "Already tested" not in llm.calls[0]["system"]
