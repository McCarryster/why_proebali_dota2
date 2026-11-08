from langchain_core.messages import AIMessage
from langgraph.graph import END

from coach.systems.langgraph.investigator import after_verify, route


def call(name: str, id: str = "x") -> dict:
    return {"name": name, "args": {}, "id": id}


def state_with(*names: str, tool_calls: int = 0, finding=None, attempts: int = 0) -> dict:
    reply = AIMessage(content="", tool_calls=[call(n, f"id{i}") for i, n in enumerate(names)])
    return {"messages": [reply], "tool_calls": tool_calls, "finding": finding, "attempts": attempts}


# route: after the model replied

def test_route_submit_goes_to_verify():
    assert route(state_with("submit_finding"), max_tool_calls=8) == "verify"


def test_route_submit_wins_even_over_budget():
    assert route(state_with("submit_finding", tool_calls=99), max_tool_calls=8) == "verify"


def test_route_tool_call_within_budget_goes_to_tools():
    assert route(state_with("fetch_match", tool_calls=1), max_tool_calls=8) == "tools"


def test_route_budget_boundary():
    # `tool_calls` counts calls REQUESTED so far (including this reply), so the limit itself is allowed
    assert route(state_with("fetch_match", tool_calls=8), max_tool_calls=8) == "tools"
    assert route(state_with("fetch_match", tool_calls=9), max_tool_calls=8) == END


def test_route_no_tool_call_ends():
    assert route(state_with(), max_tool_calls=8) == END


def test_route_mixed_batch_with_submit_goes_to_verify():
    # verify answers the whole batch with an error: the model must submit alone
    assert route(state_with("fetch_match", "submit_finding"), max_tool_calls=8) == "verify"


# after_verify: after the verify node ran

def test_after_verify_finding_ends():
    assert after_verify(state_with(finding={"claim": "c"}, attempts=1), max_attempts=2) == END


def test_after_verify_retry_when_attempts_left():
    assert after_verify(state_with(attempts=1), max_attempts=2) == "model"


def test_after_verify_attempts_used_up_ends():
    assert after_verify(state_with(attempts=2), max_attempts=2) == END


def test_after_verify_finding_beats_attempts():
    assert after_verify(state_with(finding={"claim": "c"}, attempts=2), max_attempts=2) == END
