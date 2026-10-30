import asyncio
from langfuse import get_client
from dataclasses import dataclass

from coach import llm
from coach.schemas import Plan, Hypothesis, Report
from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.investigator import InvestigationResult, run_investigator
from coach.systems.scratch.planner import make_plan
from coach.systems.scratch.reporter import write_report
from coach.systems.scratch.state import RunState, decide


@dataclass
class RunResult:
    report: Report
    state: RunState


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


def update_state(state: RunState, plan: Plan, results: dict[str, InvestigationResult | BaseException]) -> None:
    for h in plan.hypotheses:
        result = results[h.id]
        state.hypotheses_tried.append(h.statement)
        if isinstance(result, BaseException):
            state.dropped.append(h.id)
            continue
        state.tokens_spent += result.tokens
        if result.finding is None:
            state.dropped.append(h.id)
        else:
            state.findings.append(result.finding)


async def run_orchestrator(question: str, match_id: int, tools: McpTools, llm_call=llm.call) -> RunResult:
    plan = await make_plan(question, match_id, tools, llm_call=llm_call)
    state = RunState(question=question, match_id=match_id)
    while True:
        results = await investigate_all(plan, match_id, tools, llm_call=llm_call)
        update_state(state, plan, results)
        decision = decide(state)
        if decision.action == "finish":
            break
        state.iteration += 1
        plan = await make_plan(question, match_id, tools, llm_call=llm_call, avoid=state.hypotheses_tried)

    report = await write_report(state, tools, llm_call=llm_call)

    return RunResult(report=report, state=state)