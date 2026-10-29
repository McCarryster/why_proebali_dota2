import asyncio

from coach.schemas import Plan, Hypothesis
from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.orchestrator import investigate_all
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