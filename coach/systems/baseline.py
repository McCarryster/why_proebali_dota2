from coach.schemas import Report
from coach.dota.opendota import get_match
from coach.dota.digest import digest
from coach.llm import call
from coach.prompt import DOTA_ANALYST_SYSTEM_PROMPT

MAX_TOKENS = 4000

REPORT_TOOL = {
    "name": "submit_report",
    "description": "Submit the final analysis report for the match. Call exactly once.",
    "input_schema": Report.model_json_schema(),
}


def run_baseline(match_id: int,
                 question: str = "What were the key mistakes?") -> Report:
    match = get_match(match_id)
    match_digest = digest(match)


    result = call(
        [{"role": "user",
          "content": f"{match_digest}\n\nQuestion: {question}"}],
        system=DOTA_ANALYST_SYSTEM_PROMPT,
        tools=[REPORT_TOOL],
        name="baseline",
        max_tokens=MAX_TOKENS,
    )

    if result["stop_reason"] == "max_tokens":
        raise RuntimeError("Output truncated at max_tokens; report would be incomplete")

    block = next((b for b in result["content"] if b["type"] == "tool_use"), None)
    if block is None:
        texts = [b.get("text", "") for b in result["content"] if b["type"] == "text"]
        raise RuntimeError(f"Model did not call submit_report. It said: {texts}")

    return Report.model_validate(block["input"])
