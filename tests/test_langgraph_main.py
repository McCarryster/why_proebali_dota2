from langgraph.graph import END
from langgraph.types import Send
import pytest

from coach.schemas import Evidence, Finding
from coach.systems.langgraph.main_graph import after_decide, decide_node, fan_out, to_run_state


def finding_dict(verdict: str = "supported") -> dict:
    return Finding(
        claim="Dragon Knight died 9 times.",
        verdict=verdict,  # type: ignore[arg-type]
        severity="major",
        evidence=[Evidence(kind="stat", player="Dragon Knight (Radiant)", metric="deaths", value=9)],
    ).model_dump()


def ok(hid: str, verdict: str = "supported") -> dict:
    return {"hypothesis_id": hid, "status": "ok", "reason": "submitted", "finding": finding_dict(verdict)}


def error(hid: str) -> dict:
    return {"hypothesis_id": hid, "status": "error", "error": "boom"}


def state_with(results: list[dict], tokens: int = 10_000, iteration: int = 0) -> dict:
    plan = {"question": "q", "hypotheses": [{"id": "H1", "statement": "s", "rationale": "r"}]}
    return {"question": "q", "match_id": "9041884546", "plan": plan, "tokens": tokens,
            "results": results, "iteration": iteration, "decisions": [], "action": None}


# fan_out

def test_fan_out_one_send_per_hypothesis():
    hyps = [{"id": "H1", "statement": "a", "rationale": "r"}, {"id": "H2", "statement": "b", "rationale": "r"}]
    state = state_with([])
    state["plan"] = {"question": "q", "hypotheses": hyps}
    sends = fan_out(state)  # type: ignore[arg-type]
    assert [type(s) for s in sends] == [Send, Send]
    assert [s.node for s in sends] == ["investigate", "investigate"]
    assert [s.arg["hypothesis"]["id"] for s in sends] == ["H1", "H2"]
    assert all(s.arg["match_id"] == "9041884546" for s in sends)


def test_fan_out_without_plan_raises():
    state = state_with([])
    state["plan"] = None
    with pytest.raises(RuntimeError):
        fan_out(state)  # type: ignore[arg-type]


# to_run_state

def test_to_run_state_converts_types_and_copies_numbers():
    rs = to_run_state(state_with([ok("H1")], tokens=1234, iteration=1))  # type: ignore[arg-type]
    assert rs.match_id == 9041884546          # str in LangGraph state, int in RunState
    assert rs.tokens_spent == 1234
    assert rs.iteration == 1
    assert len(rs.findings) == 1


def test_to_run_state_skips_errors_and_missing_findings():
    results = [ok("H1"), error("H2"), {"hypothesis_id": "H3", "status": "ok", "finding": None}]
    rs = to_run_state(state_with(results))  # type: ignore[arg-type]
    assert len(rs.findings) == 1


# decide_node (rules themselves are tested in test_state.py; here we test the wiring to them)

def test_decide_finishes_with_enough_evidence():
    out = decide_node(state_with([ok("H1"), ok("H2"), ok("H3")]))  # type: ignore[arg-type]
    assert out["action"] == "finish"
    assert len(out["decisions"]) == 1 and out["decisions"][0].startswith("finish")
    assert "iteration" not in out


def test_decide_replans_and_increments_iteration():
    out = decide_node(state_with([ok("H1"), error("H2"), error("H3")]))  # type: ignore[arg-type]
    assert out["action"] == "replan"
    assert out["iteration"] == 1


def test_decide_inconclusive_findings_do_not_count():
    results = [ok("H1", "inconclusive"), ok("H2", "inconclusive"), ok("H3")]
    assert decide_node(state_with(results))["action"] == "replan"  # type: ignore[arg-type]


def test_decide_records_all_statements_as_tried():
    state = state_with([ok("H1"), ok("H2"), ok("H3")])
    state["plan"] = {"question": "q", "hypotheses": [
        {"id": "H1", "statement": "first", "rationale": "r"},
        {"id": "H2", "statement": "second", "rationale": "r"},
    ]}
    out = decide_node(state)  # type: ignore[arg-type]
    assert out["hypotheses_tried"] == ["first", "second"]


def test_decide_without_plan_raises():
    state = state_with([ok("H1")])
    state["plan"] = None
    with pytest.raises(RuntimeError):
        decide_node(state)  # type: ignore[arg-type]


# after_decide

def test_after_decide_replan_goes_to_plan():
    assert after_decide({"action": "replan"}) == "plan"  # type: ignore[arg-type]


def test_after_decide_finish_ends():
    assert after_decide({"action": "finish"}) == END  # type: ignore[arg-type]


def test_decide_finishes_when_token_budget_spent():
    out = decide_node(state_with([error("H1")], tokens=150_000))  # type: ignore[arg-type]
    assert out["action"] == "finish"
