import asyncio

from coach.schemas import Plan, Hypothesis
from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.orchestrator import investigate_all

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


def test_investigate_all():
    llm = RoutedFakeLLM({PLAN.hypotheses[0].statement, })
    results = run(llm)
    assert ...   # three of them
