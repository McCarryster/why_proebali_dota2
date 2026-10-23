"""One investigator: a tool-calling loop that tests ONE hypothesis about ONE match.

The model picks tools (via MCP) until it calls `submit_finding`; every evidence item in that
finding is then checked deterministically with `verify_claim`. A wrong finding is sent back to
the model with the actual values (bounded retries).
"""
from dataclasses import dataclass

from pydantic import ValidationError

from coach import llm
from coach.schemas import Finding
from coach.systems.scratch.mcp_tools import McpTools


@dataclass
class InvestigationResult:
    finding: Finding | None
    tool_calls: int
    reason: str          # "submitted" | "budget" | "invalid" | "no_tool_call"


# A LOCAL tool: it is the loop's way out, not something the MCP server offers.
SUBMIT_FINDING_TOOL = {
    "name": "submit_finding",
    "description": "Submit your final finding for the hypothesis. Call it once, alone, after "
                   "you have verified your evidence with verify_claim.",
    "input_schema": Finding.model_json_schema(),
}


async def run_investigator(hypothesis: str, match_id: int, tools: McpTools,
                           llm_call=llm.call, max_tool_calls: int = 8,
                           max_attempts: int = 2) -> InvestigationResult:
    system = await tools.prompt("investigator", {"hypothesis": hypothesis, "match_id": str(match_id)})
    defs = tools.definitions() + [SUBMIT_FINDING_TOOL]
    messages = [{"role": "user", "content": "Begin the investigation."}]
    tool_calls = 0
    attempts_left = max_attempts

    while tool_calls < max_tool_calls:
        reply = llm_call(messages, system=system, tools=defs, name="investigator")

        # TODO 1: if reply["stop_reason"] == "max_tokens": raise RuntimeError(...)
        # TODO 2: tool_use_blocks = the blocks of reply["content"] whose "type" is "tool_use"
        #         if there are none: return InvestigationResult(None, tool_calls, "no_tool_call")
        # TODO 3: if one block is named "submit_finding": validate it and verify its evidence
        #         (see the spec); return, or build an is_error tool_result and keep looping
        # TODO 4: otherwise run each tool with `await tools.call(name, input)` and build one
        #         tool_result block per tool_use block
        # TODO 5: append the assistant reply and ONE user message holding ALL tool_results
        ...

    return InvestigationResult(None, tool_calls, "budget")
