import operator
from typing import TypedDict, Annotated
from collections.abc import Callable, Awaitable

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import BaseTool
from langchain_core.runnables import RunnableConfig

from langgraph.types import Send
from langgraph.graph import StateGraph, START, END

from coach.schemas import Finding
from coach.systems.langgraph.planner import make_plan
from coach.systems.scratch.state import RunState, decide
from coach.systems.langgraph.investigator import run_investigator


class MainState(TypedDict):
    question: str
    match_id: str
    plan: dict | None
    tokens: Annotated[int, operator.add]
    results: Annotated[list[dict], operator.add]
    iteration: int                                  # replace; 0 on the first round
    decisions: Annotated[list[str], operator.add]   # log, like scratch's state.decisions
    action: str | None                              # "finish" or "replan", read by the router later
    hypotheses_tried: Annotated[list[str], operator.add]


class InvestigateInput(TypedDict):
    match_id: str
    hypothesis: dict


GetPrompt = Callable[[str, dict[str, str]], Awaitable[str]]   # (name, args) -> prompt text


def to_run_state(state: MainState) -> RunState:
    return RunState(question=state["question"],
                    match_id=int(state["match_id"]), # int because scratch version uses int match_id
                    iteration=state["iteration"],
                    tokens_spent=state["tokens"],
                    findings=[Finding.model_validate(r["finding"]) for r in state["results"] if r.get("finding")]
                    )

def decide_node(state: MainState) -> dict:
    if state["plan"] is None:
        raise RuntimeError("decide_node called without a plan")
    decision = decide(to_run_state(state))
    tried = [h["statement"] for h in state["plan"]["hypotheses"]]
    out = {"action": decision.action, "decisions": [f"{decision.action}: {decision.reason}"], "hypotheses_tried": tried}
    if decision.action == "replan":
        out["iteration"] = state["iteration"] + 1
    return out

def after_decide(state: MainState) -> str:
    if state["action"] == "replan":
        return "plan"
    return END

def fan_out(state: MainState) -> list[Send]:
    if state["plan"] is None:
        raise RuntimeError("fan_out called without a plan")
    return [Send("investigate", {"match_id": state["match_id"], "hypothesis": h}) for h in state["plan"]["hypotheses"]]


def build_main_graph(tools: list[BaseTool], model: ChatAnthropic, get_prompt: GetPrompt,
                     max_tool_calls: int = 8, max_attempts: int = 2):

    async def investigate(state: InvestigateInput, config: RunnableConfig) -> dict:
        h = state["hypothesis"]
        try:
            prompt_text = await get_prompt("investigator", {"hypothesis": h["statement"], "match_id": state["match_id"]})
            result = await run_investigator(match_id=state["match_id"], tools=tools, model=model, prompt_text=prompt_text, 
                                      config=config, max_tool_calls=max_tool_calls, max_attempts=max_attempts)
            return {"results": [{
                    "hypothesis_id": h["id"],
                    "status": "ok",
                    "reason": result.reason,
                    "tool_calls": result.tool_calls,
                    "tokens": result.tokens,
                    "finding": result.finding.model_dump() if result.finding else None,
                }], "tokens": result.tokens}
        except Exception as e:
            return {"results": [{"hypothesis_id": h["id"], "status": "error", "error": str(e)}]}

    async def plan_node(state: MainState, config: RunnableConfig) -> dict:
        prompt_text = await get_prompt("planner", {"question": state["question"], "match_id": state["match_id"],
                                                   "avoid": "\n".join(state["hypotheses_tried"])})

        result = await make_plan(match_id=state["match_id"], tools=tools, model=model, 
                                 prompt_text=prompt_text, config=config)

        return {"plan": result.plan.model_dump(), "tokens": result.tokens}

    builder = StateGraph(MainState)
    
    builder.add_node("plan", plan_node)
    builder.add_node("investigate", investigate)
    builder.add_node("decide", decide_node)

    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", fan_out)
    builder.add_edge("investigate", "decide")
    builder.add_conditional_edges("decide", after_decide)

    return builder.compile()