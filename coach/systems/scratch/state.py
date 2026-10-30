from pydantic import BaseModel, Field
from typing import Literal

from coach.schemas import Finding


class Decision(BaseModel):
    action: Literal["finish", "replan"] = Field()
    reason: str = Field()


class RunState(BaseModel):
    question: str = Field()
    match_id: int = Field()
    iteration: int = Field(default=0)
    findings: list[Finding] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
    hypotheses_tried: list[str] = Field(default_factory=list)
    tokens_spent: int = Field(default=0)


def decide(state: RunState, max_iterations: int = 2, min_findings: int = 2,
           max_tokens: int = 100_000) -> Decision:
    if state.tokens_spent >= max_tokens:
        return Decision(action="finish", reason=f"token budget spent ({state.tokens_spent}/{max_tokens})")
    if state.iteration + 1 >= max_iterations:
        return Decision(action="finish", reason=f"iteration limit reached ({state.iteration + 1}/{max_iterations})")

    # An inconclusive finding answers nothing, so it does not count as evidence.
    useful = [f for f in state.findings if f.verdict != "inconclusive"]

    if len(useful) >= min_findings:
        return Decision(action="finish", reason=f"enough evidence ({len(useful)} useful findings, need {min_findings})")
    else:
        return Decision(action="replan", reason=f"not enough evidence ({len(useful)} useful findings, need {min_findings}); budget remains")