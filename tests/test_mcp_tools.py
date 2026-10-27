import asyncio

from coach.systems.scratch.mcp_tools import McpTools
from coach.tools.handwired import definitions

MATCH = 9041878637
WRONG = {"kind": "timeline", "metric": "gold_adv", "time_s": 1320, "value": -30596}


def _strip_titles(x):
    if isinstance(x, dict):
        return {k: _strip_titles(v) for k, v in x.items() if k != "title"}
    if isinstance(x, list):
        return [_strip_titles(i) for i in x]
    return x

def test_definitions_match_handwired():
    async def run():
        async with McpTools() as t:
            return t.definitions()
    mcp_defs = {d["name"]: d for d in asyncio.run(run())}
    for d in definitions():
        mine = mcp_defs[d["name"]]
        assert _strip_titles(mine["input_schema"]) == _strip_titles(d["input_schema"])
        assert mine["description"] == d["description"]

def test_false_claim_is_an_answer_not_an_error():
    async def run():
        async with McpTools() as t:
            return await t.call("verify_claim", {"match_id": MATCH, "evidence": WRONG})
    text, is_error = asyncio.run(run())
    assert not is_error                       # a false claim is an answer, not bad input
    assert text.startswith("MISMATCH") and "1260s" in text


def test_bad_argument_is_reported_as_error():
    async def run():
        async with McpTools() as t:
            return await t.call("fetch_match", {"match_id": "abc"})
    text, is_error = asyncio.run(run())
    assert is_error
    assert "match_id" in text


def test_investigator_prompt_is_served_with_blanks_filled():
    async def run():
        async with McpTools() as t:
            return await t.prompt("investigator", {"hypothesis": "Radiant lost the 10:41 fight",
                                                   "match_id": "9041878637"})
    text = asyncio.run(run())
    assert "Radiant lost the 10:41 fight" in text
    assert "verify_claim" in text and "get_events" in text and "submit_finding" in text


def test_planner_prompt_is_served_with_blanks_filled():
    async def run():
        async with McpTools() as t:
            return await t.prompt("planner", {"question": "What were the key mistakes?",
                                              "match_id": "9041878637"})
    text = asyncio.run(run())
    assert "What were the key mistakes?" in text and "9041878637" in text
    assert "submit_plan" in text
