"""The investigator loop against a scripted fake model.

Real: the MCP server subprocess (via McpTools), the tools, verify_claim, Pydantic validation.
Fake: the model (FakeLLM replays scripted replies). No API calls, no cost.
"""
import asyncio

from coach.systems.scratch.investigator import run_investigator
from coach.systems.scratch.mcp_tools import McpTools
from tests.fakes import FakeLLM, reply, tool_use

MATCH = 9041878637

GET_DK_DEATHS = tool_use("get_events", {"match_id": MATCH, "player": "Dragon Knight (Radiant)",
                                        "event_type": "deaths"})

GOOD_FINDING = {
    "claim": "Dragon Knight died 9 times.",
    "verdict": "supported",
    "severity": "major",
    "evidence": [{"kind": "stat", "player": "Dragon Knight (Radiant)", "metric": "deaths", "value": 9}],
}

# Well-formed, but false: the real gold_adv at 1320s is -50352 (-30596 is the value at 1260s).
WRONG_VALUE_FINDING = {
    "claim": "Dire led by 30596 gold at 22:00.",
    "verdict": "supported",
    "severity": "major",
    "evidence": [{"kind": "timeline", "metric": "gold_adv", "time_s": 1320, "value": -30596}],
}

# Not even well-formed: no claim.
MISSING_CLAIM_FINDING = {k: v for k, v in GOOD_FINDING.items() if k != "claim"}


def run(llm, **kwargs):
    async def go():
        async with McpTools() as tools:
            return await run_investigator("test hypothesis", MATCH, tools, llm_call=llm, **kwargs)
    return asyncio.run(go())


def last_message(llm, call_index):
    return llm.calls[call_index]["messages"][-1]


def test_happy_path_submits_a_verified_finding():
    llm = FakeLLM([reply(GET_DK_DEATHS), reply(tool_use("submit_finding", GOOD_FINDING))])
    result = run(llm)

    assert result.reason == "submitted"
    assert result.finding.verdict == "supported"
    assert result.tool_calls == 1                      # get_events counts; submit_finding does not
    tool_result = last_message(llm, 1)["content"][0]   # the 2nd model call saw the tool's output
    assert tool_result["type"] == "tool_result"
    assert "killed by" in tool_result["content"]


def test_wrong_value_is_sent_back_with_the_real_value_then_fixed():
    llm = FakeLLM([reply(tool_use("submit_finding", WRONG_VALUE_FINDING)),
                   reply(tool_use("submit_finding", GOOD_FINDING))])
    result = run(llm)

    assert result.reason == "submitted"
    feedback = last_message(llm, 1)["content"][0]
    assert feedback["is_error"] is True
    assert "MISMATCH" in feedback["content"] and "1260s" in feedback["content"]


def test_malformed_finding_is_sent_back_naming_the_field():
    llm = FakeLLM([reply(tool_use("submit_finding", MISSING_CLAIM_FINDING)),
                   reply(tool_use("submit_finding", GOOD_FINDING))])
    result = run(llm)

    assert result.reason == "submitted"
    feedback = last_message(llm, 1)["content"][0]
    assert feedback["is_error"] is True and "claim" in feedback["content"]


def test_two_wrong_submissions_drop_the_finding():
    llm = FakeLLM([reply(tool_use("submit_finding", WRONG_VALUE_FINDING)),
                   reply(tool_use("submit_finding", WRONG_VALUE_FINDING))])
    result = run(llm, max_attempts=2)

    assert result.reason == "invalid"
    assert result.finding is None
    assert len(llm.calls) == 2                         # exactly max_attempts submissions, no more


def test_a_model_that_never_submits_hits_the_tool_call_budget():
    llm = FakeLLM([reply(GET_DK_DEATHS) for _ in range(3)])
    result = run(llm, max_tool_calls=3)

    assert result.reason == "budget"
    assert result.finding is None
    assert result.tool_calls == 3
    assert len(llm.calls) == 3                         # the loop did not ask a 4th time


def test_a_reply_without_any_tool_call_ends_the_run():
    llm = FakeLLM([reply({"type": "text", "text": "I think Radiant lost."}, stop_reason="end_turn")])
    result = run(llm)

    assert result.reason == "no_tool_call"
    assert result.finding is None


def test_a_tool_error_is_fed_back_to_the_model_not_raised():
    bad_player = tool_use("get_events", {"match_id": MATCH, "player": "Drow (Radiant)",
                                         "event_type": "deaths"})
    llm = FakeLLM([reply(bad_player), reply(tool_use("submit_finding", GOOD_FINDING))])
    result = run(llm)

    assert result.reason == "submitted"
    feedback = last_message(llm, 1)["content"][0]
    assert feedback["is_error"] is True
    assert "Drow Ranger (Radiant)" in feedback["content"]    # the error lists the valid labels


def test_submit_mixed_with_another_tool_is_rejected_but_the_other_tool_is_answered():
    # The model submits in the same reply as a tool call: it has not seen that tool's result yet.
    mixed = reply(tool_use("get_events", {"match_id": MATCH, "player": "Dragon Knight (Radiant)",
                                          "event_type": "deaths"}, id="toolu_events"),
                  tool_use("submit_finding", GOOD_FINDING, id="toolu_submit"))
    llm = FakeLLM([mixed, reply(tool_use("submit_finding", GOOD_FINDING))])
    result = run(llm)

    assert result.reason == "submitted"                      # it is accepted on the second try
    assert result.tool_calls == 1                            # only get_events was run
    results = {r["tool_use_id"]: r for r in last_message(llm, 1)["content"]}
    assert set(results) == {"toolu_events", "toolu_submit"}  # EVERY request gets an answer
    assert not results["toolu_events"]["is_error"]
    assert "killed by" in results["toolu_events"]["content"]
    assert results["toolu_submit"]["is_error"] is True
    assert "alone" in results["toolu_submit"]["content"]
