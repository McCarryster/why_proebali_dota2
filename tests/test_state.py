from coach.schemas import Evidence, Finding, Hypothesis, Plan
from coach.systems.scratch.investigator import InvestigationResult
from coach.systems.scratch.orchestrator import update_state
from coach.systems.scratch.state import RunState, decide


def finding(verdict="supported"):
    return Finding(
        claim="Dragon Knight died 9 times.",
        verdict=verdict,
        severity="major",
        evidence=[Evidence(kind="stat", player="Dragon Knight (Radiant)", metric="deaths", value=9)],
    )


def state(**overrides):
    return RunState(question="why lost?", match_id=1, **overrides)


def test_a_new_state_starts_empty():
    s = state()
    assert s.iteration == 0 and s.tokens_spent == 0
    assert s.findings == [] and s.dropped == [] and s.hypotheses_tried == []


def test_two_useful_findings_finish():
    d = decide(state(findings=[finding(), finding("refuted")]))
    assert d.action == "finish"
    assert "enough evidence" in d.reason


def test_inconclusive_findings_do_not_count_as_evidence():
    d = decide(state(findings=[finding(), finding("inconclusive")]))
    assert d.action == "replan"
    assert "1 useful" in d.reason


def test_no_findings_with_budget_left_replans():
    assert decide(state()).action == "replan"


def test_last_iteration_finishes_even_without_findings():
    # Budget wins over missing evidence, otherwise the loop could never end.
    d = decide(state(iteration=1), max_iterations=2)
    assert d.action == "finish"
    assert "iteration" in d.reason


def test_spent_token_budget_finishes():
    d = decide(state(tokens_spent=100_000), max_tokens=100_000)
    assert d.action == "finish"
    assert "token" in d.reason


def test_token_limit_is_checked_before_enough_evidence():
    d = decide(state(tokens_spent=200_000, findings=[finding(), finding()]), max_tokens=100_000)
    assert "token" in d.reason


PLAN = Plan(hypotheses=[Hypothesis(id="H1", statement="Dragon Knight died too often.", rationale="r")])


def test_update_state_keeps_a_finding():
    s = state()
    f = finding()
    update_state(s, PLAN, {"H1": InvestigationResult(finding=f, tool_calls=2, reason="submitted")})
    assert s.findings == [f]
    assert s.dropped == []
    assert s.hypotheses_tried == ["Dragon Knight died too often."]


def test_update_state_drops_an_investigation_without_a_finding():
    s = state()
    update_state(s, PLAN, {"H1": InvestigationResult(finding=None, tool_calls=8, reason="budget")})
    assert s.findings == []
    assert s.dropped == ["H1"]
    assert s.hypotheses_tried == ["Dragon Knight died too often."]


def test_update_state_drops_a_crashed_investigation():
    s = state()
    update_state(s, PLAN, {"H1": RuntimeError("boom")})
    assert s.findings == []
    assert s.dropped == ["H1"]
    assert s.hypotheses_tried == ["Dragon Knight died too often."]


def test_update_state_counts_tokens_even_without_a_finding():
    s = state(tokens_spent=100)
    update_state(s, PLAN, {"H1": InvestigationResult(finding=None, tool_calls=8, reason="budget", tokens=150)})
    assert s.tokens_spent == 250


def test_update_state_adds_tokens_of_a_finding():
    s = state()
    update_state(s, PLAN, {"H1": InvestigationResult(finding=finding(), tool_calls=1, reason="submitted", tokens=150)})
    assert s.tokens_spent == 150


def test_update_state_cannot_count_tokens_of_a_crash():
    s = state()
    update_state(s, PLAN, {"H1": RuntimeError("boom")})
    assert s.tokens_spent == 0
