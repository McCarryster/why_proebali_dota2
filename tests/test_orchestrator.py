import asyncio

import pytest

from coach.schemas import Plan, Hypothesis
from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.orchestrator import investigate_all, run_orchestrator
from coach.systems.scratch.checkpoint import load_checkpoint
from coach.systems.scratch.investigator import InvestigationResult

from tests.fakes import RoutedFakeLLM, reply, tool_use


MATCH = 9041878637


PLAN = Plan(hypotheses=[
    Hypothesis(id="H1", statement="Radiant lost the fight.", rationale="r1"),
    Hypothesis(id="H2", statement="Dragon Knight died too often.", rationale="r2"),
])


def finding(claim):
    return {"claim": claim, "verdict": "supported", "severity": "major",
            "evidence": [{"kind": "stat", "player": "Dragon Knight (Radiant)", "metric": "deaths", "value": 9}]}


def run(llm, **kwargs):
    async def go():
        async with McpTools() as tools:
            return await investigate_all(PLAN, MATCH, tools, llm_call=llm, **kwargs)
    return asyncio.run(go())


def test_each_hypothesis_gets_its_own_result():
    llm = RoutedFakeLLM({PLAN.hypotheses[0].statement: [reply(tool_use("submit_finding", finding("CLAIM-1")))],
                         PLAN.hypotheses[1].statement: [reply(tool_use("submit_finding", finding("CLAIM-2")))]})
    results = run(llm)
    assert set(results) == {"H1", "H2"}

    r1 = results["H1"]
    r2 = results["H2"]
    assert isinstance(r1, InvestigationResult)
    assert isinstance(r2, InvestigationResult)
    assert r1.finding is not None
    assert r2.finding is not None
    assert r1.finding.claim == "CLAIM-1"
    assert r2.finding.claim == "CLAIM-2"


def test_one_failing_investigator_does_not_lose_the_others():
    llm = RoutedFakeLLM({PLAN.hypotheses[0].statement: [reply(tool_use("submit_finding", finding("CLAIM-1")))],
                         PLAN.hypotheses[1].statement: [reply(stop_reason="max_tokens")]})   # H2 raises RuntimeError
    results = run(llm)

    assert set(results) == {"H1", "H2"}
    r1 = results["H1"]
    assert isinstance(r1, InvestigationResult)
    assert r1.finding is not None
    assert r1.finding.claim == "CLAIM-1"
    assert isinstance(results["H2"], RuntimeError)       # the error is a value in the dict, not raised

def plan_input(*statements):
    return {"hypotheses": [{"id": f"H{i}", "statement": s, "rationale": "r"} for i, s in enumerate(statements, 1)]}


def test_replan_after_an_inconclusive_round_then_finish():
    q = "QUESTION-X"
    planner_key = "You plan the investigation"
    reporter_key = "You write the final report"
    # Routes are chosen by text in the system prompt. The planner and reporter prompts both contain the question,
    # so each key is a phrase unique to its prompt. The planner key goes first: its round-2 prompt also contains
    # the earlier hypothesis statements, which are the investigator keys.
    llm = RoutedFakeLLM({
        planner_key: [reply(tool_use("submit_plan", plan_input("Radiant lost the fight.", "Dragon Knight died too often."))),
            reply(tool_use("submit_plan", plan_input("Tusk bought blink late.")))],
        "Radiant lost the fight.": [reply(tool_use("submit_finding", finding("CLAIM-1")))],
        "Dragon Knight died too often.": [reply(tool_use("submit_finding", dict(finding("CLAIM-2"), verdict="inconclusive")))],
        "Tusk bought blink late.": [reply(tool_use("submit_finding", finding("CLAIM-3")))],
        reporter_key: [reply(tool_use("submit_report", {"answer": "ANSWER", "turning_point_s": None, "unresolved": []}))],
    })

    async def go():
        async with McpTools() as tools:
            return await run_orchestrator(q, MATCH, tools, llm_call=llm)
    result = asyncio.run(go())
    state = result.state

    assert result.report.answer == "ANSWER"
    assert [f.claim for f in result.report.key_findings] == ["CLAIM-1", "CLAIM-3"]   # CLAIM-2 is inconclusive

    assert state.iteration == 1                                    # one replan happened
    assert [f.claim for f in state.findings] == ["CLAIM-1", "CLAIM-2", "CLAIM-3"]
    assert state.dropped == []
    assert state.hypotheses_tried == ["Radiant lost the fight.", "Dragon Knight died too often.", "Tusk bought blink late."]

    planner_calls = [c for c in llm.calls if c["key"] == planner_key]
    assert len(planner_calls) == 2
    assert "Already tested" not in planner_calls[0]["system"]
    assert "Radiant lost the fight." in planner_calls[1]["system"]  # the replan was told what was already tried
    # Each fake reply reports 100 + 50 tokens and each investigator made exactly one call (the planner is not counted).
    assert state.tokens_spent == 3 * 150
    # Every round leaves its decision in the state, in order, so a trace can explain why the loop stopped.
    assert [d.split(":")[0] for d in state.decisions] == ["replan", "finish"]


PLANNER_KEY = "You plan the investigation"
REPORTER_KEY = "You write the final report"
DRAFT = {"answer": "ANSWER", "turning_point_s": None, "unresolved": []}


def run_with_checkpoint(llm, path, q="QUESTION-X"):
    async def go():
        async with McpTools() as tools:
            return await run_orchestrator(q, MATCH, tools, llm_call=llm, checkpoint_path=path)
    return asyncio.run(go())


def test_resume_after_a_crash_in_the_report_skips_all_earlier_work(tmp_path):
    path = tmp_path / "checkpoint.json"
    ok = [reply(tool_use("submit_finding", finding("CLAIM-1")))]
    ok2 = [reply(tool_use("submit_finding", finding("CLAIM-2")))]
    first = RoutedFakeLLM({
        PLANNER_KEY: [reply(tool_use("submit_plan", plan_input("Radiant lost the fight.", "Dragon Knight died too often.")))],
        "Radiant lost the fight.": ok,
        "Dragon Knight died too often.": ok2,
        # no reporter route: the run crashes when it tries to write the report
    })
    with pytest.raises(AssertionError, match="no route"):
        run_with_checkpoint(first, path)

    saved = load_checkpoint(path)
    assert saved is not None and saved.plan is None           # the rounds were finished and saved
    assert len(saved.state.findings) == 2

    second = RoutedFakeLLM({REPORTER_KEY: [reply(tool_use("submit_report", DRAFT))]})   # nothing else is available
    result = run_with_checkpoint(second, path)

    assert [c["key"] for c in second.calls] == [REPORTER_KEY]  # no planner, no investigators
    assert [f.claim for f in result.report.key_findings] == ["CLAIM-1", "CLAIM-2"]


def test_resume_after_a_crash_in_the_replan_does_not_plan_round_one_again(tmp_path):
    path = tmp_path / "checkpoint.json"
    first = RoutedFakeLLM({
        PLANNER_KEY: [reply(tool_use("submit_plan", plan_input("Radiant lost the fight.", "Dragon Knight died too often.")))],
        "Radiant lost the fight.": [reply(tool_use("submit_finding", finding("CLAIM-1")))],
        "Dragon Knight died too often.": [reply(tool_use("submit_finding", dict(finding("CLAIM-2"), verdict="inconclusive")))],
        # only one planner reply: the replan after round 1 crashes
    })
    with pytest.raises(AssertionError, match="ran out of replies"):
        run_with_checkpoint(first, path)

    saved = load_checkpoint(path)
    assert saved is not None and saved.plan is not None       # the round-1 plan was saved
    assert [h.id for h in saved.plan.hypotheses] == ["H1", "H2"]

    second = RoutedFakeLLM({
        PLANNER_KEY: [reply(tool_use("submit_plan", plan_input("Tusk bought blink late.")))],   # the replan only
        "Radiant lost the fight.": [reply(tool_use("submit_finding", finding("CLAIM-1")))],
        "Dragon Knight died too often.": [reply(tool_use("submit_finding", dict(finding("CLAIM-2"), verdict="inconclusive")))],
        "Tusk bought blink late.": [reply(tool_use("submit_finding", finding("CLAIM-3")))],
        REPORTER_KEY: [reply(tool_use("submit_report", DRAFT))],
    })
    result = run_with_checkpoint(second, path)

    assert len([c for c in second.calls if c["key"] == PLANNER_KEY]) == 1     # round 1 was not planned again
    assert [f.claim for f in result.state.findings] == ["CLAIM-1", "CLAIM-2", "CLAIM-3"]   # nothing counted twice
    final = load_checkpoint(path)
    assert final is not None and final.plan is None
