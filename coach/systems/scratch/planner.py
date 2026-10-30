from pydantic import ValidationError

from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.utils import format_errors
from coach.schemas import Plan
from coach import llm


SUBMIT_PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit the investigation plan: 1 to 5 distinct, testable hypotheses with ids H1, H2, ... "
                   "Call it once, after reading the match overview.",
    "input_schema": Plan.model_json_schema(),
}


async def make_plan(question: str, match_id: int, tools: McpTools, llm_call=llm.call, avoid: list[str] | None = None) -> Plan:
    overview, is_error = await tools.call("fetch_match", {"match_id": match_id})
    if is_error:
        raise RuntimeError(f"Could not fetch match {match_id}: {overview}")
    
    # system = await tools.prompt("planner", {"question": question, "match_id": str(match_id)})
    system = await tools.prompt("planner", {"question": question, "match_id": str(match_id),
                                        "avoid": "\n".join(avoid or [])})
    messages = [{"role": "user", "content": overview}]

    for _ in range(2):
        reply = llm_call(messages, system=system, tools=[SUBMIT_PLAN_TOOL], name="planner")
        if reply["stop_reason"] == "max_tokens":
            raise RuntimeError("Hit max tokens limit")

        submit = next((b for b in reply["content"] if b["type"] == "tool_use" and b["name"] == "submit_plan"), None)
        if submit is None:
            raise RuntimeError("Planner did not call submit_plan")   # the model ignored the tool: not fixable by retry

        try:
            return Plan.model_validate(submit["input"])              # success
        except ValidationError as e:
            messages = messages + [
                {"role": "assistant", "content": reply["content"]},
                {"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": submit["id"], "is_error": True,
                    "content": "Your plan failed verification:\n" + "\n".join([format_errors(e)])
                                + "\nFix it and call submit_plan again.",
                }]},
            ]

    raise RuntimeError("Planner failed to produce a valid plan in 2 attempts")