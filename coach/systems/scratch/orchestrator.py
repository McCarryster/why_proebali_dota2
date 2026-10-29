import asyncio

from langfuse import get_client

from coach import llm
from coach.schemas import Plan, Hypothesis
from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.investigator import InvestigationResult, run_investigator


async def _traced_investigation(h: Hypothesis, match_id: int, tools: McpTools, llm_call=llm.call):
    lf = get_client()
    with lf.start_as_current_observation(as_type="agent", name=f"investigator-{h.id}",
                                            input={"hypothesis": h.statement}) as span:
        try:
            result = await run_investigator(h.statement, match_id, tools, llm_call=llm_call)
        except Exception as e:
            span.update(level="ERROR", status_message=str(e))
            raise
        span.update(output={"reason": result.reason, "finding": result.finding.model_dump() if result.finding else None})
        
        return result


async def investigate_all(plan: Plan, match_id: int, tools: McpTools,
                          llm_call=llm.call) -> dict[str, InvestigationResult | BaseException]:

    coros = [_traced_investigation(h, match_id, tools, llm_call=llm_call) for h in plan.hypotheses]
    results = await asyncio.gather(*coros, return_exceptions=True)
    
    return {h.id: r for h, r in zip(plan.hypotheses, results)}