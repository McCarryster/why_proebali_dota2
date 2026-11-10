from pydantic import ValidationError

from langchain_core.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from langchain_core.runnables import RunnableConfig

from coach.schemas import Plan, PlanResult
from coach.systems.langgraph.utils import block_text, format_errors


class submit_plan(Plan): # subclass trick
    """Submit the investigation plan: 1 to 5 distinct, testable hypotheses with ids H1, H2, ... Call it once, after reading the match overview."""


async def make_plan(
    match_id: str,
    tools: list[BaseTool],      # to find fetch_match
    model: ChatAnthropic,
    prompt_text: str,           # the planner prompt, fetched by the caller (it already holds question, match id, avoid)
    config: RunnableConfig | None = None,
) -> PlanResult:

    fetch = next((t for t in tools if t.name == "fetch_match"))
    try:
        r = await fetch.ainvoke({"match_id": match_id}, config=config)
        overview = block_text(r)
    except Exception as e:
        raise RuntimeError(f"Could not fetch match {match_id}") from e

    messages = [SystemMessage(content=prompt_text), HumanMessage(content=overview)]
    model_with_tool = model.bind_tools([submit_plan])

    tokens = 0
    for _ in range(2):
        reply = await model_with_tool.ainvoke(messages, config=config)

        if reply.response_metadata.get("stop_reason") == "max_tokens":
            raise RuntimeError("Hit max tokens limit")
        
        usage = reply.usage_metadata or {}
        tokens += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        
        submit = next((b for b in reply.tool_calls if b["name"] == "submit_plan"), None)
        if submit is None:
            raise RuntimeError("Planner did not call submit_plan")   # the model ignored the tool: not fixable by retry

        try:
            plan = Plan.model_validate(submit["args"]) 
            return PlanResult(plan=plan, tokens=tokens)              # success
        except ValidationError as e:
            content = f"Your plan failed verification:\n{format_errors(e)}\nFix it and call submit_plan again."
            messages = messages + [reply, ToolMessage(content=content, tool_call_id=submit["id"], status="error")]

    raise RuntimeError("Planner failed to produce a valid plan in 2 attempts")