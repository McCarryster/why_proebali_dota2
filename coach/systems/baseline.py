from coach.schemas import Report
from coach.dota.opendota import get_match
from coach.dota.digest import digest
from coach.llm import call
from coach.prompt import DOTA_ANALYST_SYSTEM_PROMPT
from pydantic import ValidationError

MAX_ATTEMPTS = 2
MAX_TOKENS = 4000

REPORT_TOOL = {
    "name": "submit_report",
    "description": "Submit the final analysis report for the match. Call exactly once.",
    "input_schema": Report.model_json_schema(),
}


def format_errors(e: ValidationError) -> str:
    return "\n".join(
        f"- {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
    )


def run_baseline(match_id: int,
                 question: str = "What were the key mistakes?") -> Report:
    match = get_match(match_id)
    match_digest = digest(match)

    messages = [{"role": "user", "content": f"{match_digest}\n\nQuestion: {question}"}]
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS+1):

        result = call(
            messages,
            system=DOTA_ANALYST_SYSTEM_PROMPT,
            tools=[REPORT_TOOL],
            name=f"baseline-attempt-{attempt}",
            max_tokens=MAX_TOKENS,
        )

        if result["stop_reason"] == "max_tokens":
            raise RuntimeError("Output truncated at max_tokens; report would be incomplete")

        block = next((b for b in result["content"] if b["type"] == "tool_use"), None)
        if block is None:
            texts = [b.get("text", "") for b in result["content"] if b["type"] == "text"]
            raise RuntimeError(f"Model did not call submit_report. It said: {texts}")

        try:
            return Report.model_validate(block["input"])
        except ValidationError as e:
            last_error = e
            messages = messages + [
                {"role": "assistant", "content": result["content"]},
                {"role": "user", "content": [{
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "is_error": True,
                    "content": f"Your report failed validation:\n{format_errors(e)}\n"
                               "Fix these fields and call submit_report again.",
                }]},
            ]

    raise RuntimeError(f"Report still invalid after {MAX_ATTEMPTS} attempts:\n{last_error}")
