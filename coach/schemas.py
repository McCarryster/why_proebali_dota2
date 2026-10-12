from typing import Literal
from pydantic import BaseModel, Field


# Names match OpenDota's player keys, so verify_claim is a direct lookup.
Metric = Literal[
    "kills", "deaths", "assists", "last_hits",
    "gold_per_min", "xp_per_min", "net_worth",
    "hero_damage", "tower_damage",
]

Verdict = Literal["supported", "refuted", "inconclusive"]

Severity = Literal["minor", "major", "decisive"]


class Evidence(BaseModel):
    player: str = Field(description="Player label exactly as in the match digest: 'Hero (Team)', e.g. 'Drow Ranger (Radiant)'")
    metric: Metric = Field(description="Which end-of-match stat is being cited")
    value: int = Field(description="The stat's value at the end of the match")


class Finding(BaseModel):
    # # hypothesis_id is added in the agent systems; the baseline has no planner
    claim: str = Field(description="One falsifiable sentence about a specific player or team, e.g. 'Drow Ranger died 9 times while Radiant lost 3 towers.'")
    verdict: Verdict = Field(description="Whether the match data supports the hypothesis being investigated")
    severity: Severity = Field(description="How much this contributed to the result")
    evidence: list[Evidence] = Field(min_length=1, description="Facts from the match that support the claim")


class Report(BaseModel):
    answer: str = Field(description="Direct answer to the question, 2-4 sentences")
    turning_point_s: int | None = Field(None, description="Match time in seconds when the game swung; the data resolution is one minute. None if there was no clear swing")
    key_findings: list[Finding] = Field(description="The most important findings, most severe first")
    unresolved: list[str] = Field(default_factory=list, description="Open questions the data could not answer")


if __name__ == "__main__":
    import json
    print(json.dumps(Evidence.model_json_schema(), indent=1))
