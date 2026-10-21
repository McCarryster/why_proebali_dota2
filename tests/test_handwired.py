import asyncio
from coach.tools.handwired import definitions, dispatch
from coach.mcp_server.server import mcp


MATCH = 9041878637


def test_definitions_have_what_the_api_needs():
    defs = definitions()
    assert {d["name"] for d in defs} == {"fetch_match", "verify_claim", "get_events"}
    for d in defs:
        assert d["description"] and d["input_schema"]["type"] == "object"


def test_fetch_match_success():
    text, is_error = dispatch("fetch_match", {"match_id": MATCH})
    assert not is_error
    assert "WINNER: Dire" in text


def test_unknown_tool_lists_available_tools():
    text, is_error = dispatch("nope", {})
    assert is_error
    assert "fetch_match" in text and "verify_claim" in text


def test_wrong_argument_type_names_the_field():
    text, is_error = dispatch("fetch_match", {"match_id": "abc"})
    assert is_error
    assert "match_id" in text


def test_missing_nested_field_is_rejected_during_argument_validation():
    # The Evidence validator runs while arguments are validated, so verify_claim never runs.
    text, is_error = dispatch("verify_claim", {
        "match_id": MATCH,
        "evidence": {"kind": "timeline", "metric": "gold_adv", "value": 1},
    })
    assert is_error
    assert "requires time_s" in text          # our validator's message reaches the model


def test_verify_claim_mismatch_is_not_an_error():
    text, is_error = dispatch("verify_claim", {
        "match_id": MATCH,
        "evidence": {"kind": "timeline", "metric": "gold_adv", "time_s": 1320, "value": -30596},
    })
    assert not is_error                       # a false claim is an answer, not bad input
    assert text.startswith("MISMATCH") and "1260s" in text


def test_unparsed_match_is_a_tool_input_error(monkeypatch):
    monkeypatch.setattr("coach.tools.core.get_match", lambda _id: {})
    text, is_error = dispatch("fetch_match", {"match_id": 1})
    assert is_error
    assert "Do not retry" in text


def _strip_titles(x):
    if isinstance(x, dict):
        return {k: _strip_titles(v) for k, v in x.items() if k != "title"}
    if isinstance(x, list):
        return [_strip_titles(i) for i in x]
    return x


def test_mcp_and_registry_expose_identical_schemas():
    mcp_schemas = {t.name: t.input_schema for t in asyncio.run(mcp.list_tools())}
    for d in definitions():
        assert _strip_titles(mcp_schemas[d["name"]]) == _strip_titles(d["input_schema"])

def test_get_events_success_and_unknown_player():
    text, is_error = dispatch("get_events", {"match_id": MATCH, "player": "Dragon Knight (Radiant)",
                                             "event_type": "deaths", "end_s": 800})
    assert not is_error and "killed by" in text
    text, is_error = dispatch("get_events", {"match_id": MATCH, "player": "Drow (Radiant)",
                                             "event_type": "deaths"})
    assert is_error and "Drow Ranger (Radiant)" in text
