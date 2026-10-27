import asyncio

from coach import llm
from coach.schemas import Plan
from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.investigator import InvestigationResult, run_investigator


async def investigate_all(plan: Plan, match_id: int, tools: McpTools,
                          llm_call=llm.call) -> dict[str, InvestigationResult | BaseException]:

    coros = [run_investigator(h.statement, match_id, tools, llm_call=llm_call) for h in plan.hypotheses]
    results = await asyncio.gather(*coros, return_exceptions=True)
    
    return {h.id: r for h, r in zip(plan.hypotheses, results)}