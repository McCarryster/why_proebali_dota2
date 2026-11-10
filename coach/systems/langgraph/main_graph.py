import operator
from typing import TypedDict, Annotated
from collections.abc import Callable, Awaitable

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import BaseTool
from langchain_core.runnables import RunnableConfig

from langgraph.graph import StateGraph, START, END

from coach.systems.langgraph.planner import make_plan


class MainState(TypedDict):
    question: str
    match_id: str
    plan: dict | None
    tokens: Annotated[int, operator.add]


GetPrompt = Callable[[str, dict[str, str]], Awaitable[str]]   # (name, args) -> prompt text


def build_main_graph(tools: list[BaseTool], model: ChatAnthropic, get_prompt: GetPrompt):

    async def plan_node(state: MainState, config: RunnableConfig) -> dict:
        prompt_text = await get_prompt("planner", {"question": state["question"], "match_id": state["match_id"], "avoid": ""})

        result = await make_plan(match_id=state["match_id"], tools=tools, model=model, 
                                 prompt_text=prompt_text, config=config)

        return {"plan": result.plan.model_dump(), "tokens": result.tokens}

    builder = StateGraph(MainState)
    builder.add_node("plan", plan_node)
    builder.add_edge(START, "plan")
    builder.add_edge("plan", END)
    
    return builder.compile()