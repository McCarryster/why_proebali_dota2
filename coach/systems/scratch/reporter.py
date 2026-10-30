
from pydantic import ValidationError

from coach import llm
from coach.schemas import ReportDraft, Report
from coach.systems.scratch.state import RunState
from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.utils import format_errors


SUBMIT_REPORT_TOOL = {
    "name": "submit_report",
    "description": "Submit the final report: a direct answer, the turning point if the data shows one, and what stays unresolved. Call it once. The findings are attached automatically; do not repeat them.",
    "input_schema": ReportDraft.model_json_schema(),
}


def format_findings(state: RunState) -> str:
    lines = [f"Question: {state.question}", "", "Findings:"]
    for i, f in enumerate(state.findings, 1):
        lines.append(f"{i}. [{f.verdict}, {f.severity}] {f.claim}")     # fill in the three parts from f
    if state.dropped:
        lines.append("")
        lines.append("Hypotheses that could not be tested: " + ", ".join(state.dropped))
    return "\n".join(lines)


async def write_report(state: RunState, tools: McpTools, llm_call=llm.call) -> Report:
    system = await tools.prompt("reporter", {"question": state.question, "match_id": str(state.match_id)})
    messages = [{"role": "user", "content": format_findings(state)}]

    for _ in range(2):
        reply = llm_call(messages, system=system, tools=[SUBMIT_REPORT_TOOL], name="reporter")
        if reply["stop_reason"] == "max_tokens":
            raise RuntimeError("Hit max tokens limit")

        submit = next((b for b in reply["content"] if b["type"] == "tool_use" and b["name"] == "submit_report"), None)
        if submit is None:
            raise RuntimeError("Reporter did not call submit_report")

        try:
            draft = ReportDraft.model_validate(submit["input"])     # can fail: the model wrote something invalid
        except ValidationError as e:
            messages = messages + [
                {"role": "assistant", "content": reply["content"]},
                {"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": submit["id"], "is_error": True,
                    "content": "Your draft failed verification:\n" + "\n".join([format_errors(e)])
                                + "\nFix it and call submit_report again.",
                }]},
            ]
            continue                                                # bad answer: go to the next attempt

        # we only get here when the answer was valid
        useful = [f for f in state.findings if f.verdict != "inconclusive"]
        ranks = {"decisive": 0, "major": 1, "minor": 2}
        key_findings = sorted(useful, key=lambda f: ranks[f.severity])
        return Report(**draft.model_dump(), key_findings=key_findings)

    raise RuntimeError("Reporter failed to produce a valid report in 2 attempts")