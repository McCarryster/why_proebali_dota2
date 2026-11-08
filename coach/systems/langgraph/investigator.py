import operator
from functools import partial
from typing import Annotated, Any
from pydantic import ValidationError

from langchain_core.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.runnables import RunnableConfig

from langgraph.prebuilt import ToolNode
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from coach.schemas import InvestigationResult, Finding
from coach.systems.langgraph.utils import format_errors, block_text


class submit_finding(Finding): # subclass trick
    """Submit your final finding for the hypothesis. Call it once, alone, after you have verified your evidence with verify_claim."""

class State(MessagesState):
    tokens: Annotated[int, operator.add]
    tool_calls: Annotated[int, operator.add]
    finding: dict | None
    attempts: Annotated[int, operator.add]


def route(state: State, max_tool_calls: int) -> str:
    last = state["messages"][-1]
    names = [call["name"] for call in last.tool_calls] # type: ignore
    if "submit_finding" in names:
        return "verify"
    elif names:
        if state["tool_calls"] > max_tool_calls: # budget spent
            return END
        return "tools"
    else:
        return END

def after_verify(state: State, max_attempts: int) -> str:
    if state["finding"] is not None:
        return END
    if state["attempts"] >= max_attempts:
        return END
    return "model"

def build_graph(tools: list[BaseTool], model: ChatAnthropic, prompt_text: str, match_id: str, max_tool_calls: int, max_attempts: int):
    """the graph factory; the nodes that need verif/model_with_tools stay inside as closures"""

    async def call_model(state: State) -> dict[str, Any]:
        messages = [system] + state["messages"]
        reply = await model_with_tools.ainvoke(messages)
        usage = reply.usage_metadata or {}
        tool_calls = [c for c in reply.tool_calls if c["name"] != "submit_finding"]
        return {"messages": [reply], 
                "tokens": usage.get("input_tokens", 0)  + usage.get("output_tokens", 0),
                "tool_calls": len(tool_calls)}
    
    async def verify(state: State) -> dict[str, Any]:
        last = state["messages"][-1]
        calls = last.tool_calls # type: ignore | list of dicts: {'name','args','id','type'}
        submit = next(c for c in calls if c["name"] == "submit_finding")

        problems = []
        if len(calls) > 1:
            problems.append("call submit_finding alone")
        else:
            try:
                finding = Finding.model_validate(submit["args"])
            except ValidationError as e:
                problems.append(format_errors(e))
            else:
                for ev in finding.evidence:
                    try:
                        r = await verif.ainvoke({"match_id": match_id, "evidence": ev.model_dump()})
                        text = block_text(r)
                        if not text.startswith("OK"):
                            problems.append(text) # e.g. "MISMATCH: gold_adv at 1320s is -50352, not -30596 (... 1260s)"
                    except Exception as e:
                        problems.append(str(e))

                if not problems:  # success path lives where `finding` is known to exist
                    msgs = [ToolMessage(content="accepted", tool_call_id=submit["id"])]
                    return {"finding": finding.model_dump(), "attempts": 1, "messages": msgs}

        msgs = [ToolMessage(content="\n".join(problems), tool_call_id=c["id"], status="error")
                for c in calls]
        return {"attempts": 1, "messages": msgs}

    system = SystemMessage(content=prompt_text)
    tool_node = ToolNode(tools)
    verif = next((t for t in tools if t.name == "verify_claim"))
    model_with_tools = model.bind_tools(tools + [submit_finding])

    builder = StateGraph(State)
    builder.add_node("model", call_model)
    builder.add_node("tools", tool_node)
    builder.add_node("verify", verify)

    builder.add_edge(START, "model")
    builder.add_edge("tools", "model")

    builder.add_conditional_edges("model", partial(route, max_tool_calls=max_tool_calls))
    builder.add_conditional_edges("verify", partial(after_verify, max_attempts=max_attempts))
    
    return builder.compile()


async def run_investigator(
    match_id: str,
    tools: list[BaseTool],          # from adapter.list_tools(), made by the caller
    model: ChatAnthropic,           # made by the caller (testable with a fake)
    prompt_text: str,               # the investigator prompt (already contains the hypothesis and match id)
    callbacks: list | None = None,  # the Langfuse CallbackHandler, if any
    max_tool_calls: int = 8,
    max_attempts: int = 2,
) -> InvestigationResult:

    graph = build_graph(tools, model, prompt_text, match_id, max_tool_calls, max_attempts)
    config: RunnableConfig = {"callbacks": callbacks or [], "recursion_limit": 25}

    initial: State = {
        "messages": [HumanMessage(content="Begin the investigation.")],
        "tokens": 0,
        "tool_calls": 0,
        "finding": None,
        "attempts": 0,
    }
    result = await graph.ainvoke(initial, config=config)
    finding = Finding.model_validate(result["finding"]) if result["finding"] is not None else None

    if result["finding"] is not None:
        reason = "submitted"
    elif result["attempts"] >= max_attempts:
        reason = "invalid"
    elif result["tool_calls"] > max_tool_calls:
        reason = "budget"
    else:
        reason = "no_tool_call"

    return InvestigationResult(finding=finding, tool_calls=result["tool_calls"],
                               reason=reason, tokens=result["tokens"])