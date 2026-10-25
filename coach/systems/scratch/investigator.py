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
from coach.systems.scratch.utils import format_errors


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
        
        if reply["stop_reason"] == "max_tokens":
            raise RuntimeError("Hit max tokens limit")
        
        tool_use_blocks = [x for x in reply['content'] if x['type'] == 'tool_use']
        if not tool_use_blocks:
            return InvestigationResult(None, tool_calls, "no_tool_call")

        submit = next((x for x in tool_use_blocks if x["name"] == "submit_finding"), None)
        others = [x for x in tool_use_blocks if x is not submit]
        # A submit only counts when it is alone: otherwise the model wrote it before seeing
        # the results of its other tool calls.
        if submit is not None and not others:
            finding = None
            try:
                finding = Finding.model_validate(submit["input"])
            except ValidationError as e:
                problems = [format_errors(e)]
            else:
                problems = []
                for ev in finding.evidence:
                    text, is_error = await tools.call("verify_claim", {"match_id": match_id, "evidence": ev.model_dump()})
                    if is_error or not text.startswith("OK"):
                        problems.append(text) # e.g. "MISMATCH: gold_adv at 1320s is -50352, not -30596 (... 1260s)"

            if not problems:                                              # outcome 1: all good
                return InvestigationResult(finding, tool_calls, "submitted")

            attempts_left -= 1
            if attempts_left == 0:                                        # outcome 2: no more chances
                return InvestigationResult(None, tool_calls, "invalid")

            messages = messages + [                                       # outcome 3: tell the model, let it fix it
                {"role": "assistant", "content": reply["content"]},
                {"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": submit["id"], "is_error": True,
                    "content": "Your finding failed verification:\n" + "\n".join(problems)
                               + "\nFix it and call submit_finding again.",
                }]},
            ]
            continue                                                      # back to the top of the while loop

        results = []
        for block in tool_use_blocks:
            if block is submit:  # only reachable when submit_finding was mixed with other tools
                results.append({"type": "tool_result", "tool_use_id": block["id"], "is_error": True,
                                "content": "submit_finding must be called alone, after you have seen the "
                                           "results of your other tool calls. Call it again when you are ready."})
                continue
            text, is_error = await tools.call(block["name"], block["input"])
            tool_calls += 1
            results.append({"type": "tool_result", "tool_use_id": block["id"], 
                            "content": text, "is_error": is_error})

        messages = messages + [
            {"role": "assistant", "content": reply["content"]},
            {"role": "user", "content": results},
        ]

    return InvestigationResult(None, tool_calls, "budget")