from typing import Literal
from pydantic import BaseModel, Field, model_validator


# Names match OpenDota's player keys, so verify_claim is a direct lookup.
# Keep Metric in sync with the two tuples below (Literal needs literal strings).
Metric = Literal[
    "kills", "deaths", "assists", "last_hits",
    "gold_per_min", "xp_per_min", "net_worth",
    "hero_damage", "tower_damage", "gold_adv", "xp_adv",
]
STAT_METRICS = ("kills", "deaths", "assists", "last_hits", "gold_per_min",
                "xp_per_min", "net_worth", "hero_damage", "tower_damage")
TIMELINE_METRICS = ("gold_adv", "xp_adv")

Verdict = Literal["supported", "refuted", "inconclusive"]

Severity = Literal["minor", "major", "decisive"]




class Evidence(BaseModel):
    player: str | None = Field(default=None, description="Player label exactly as in the match digest: 'Hero (Team)', e.g. 'Drow Ranger (Radiant)'")
    kind: Literal["stat", "timeline"] = Field(description="'stat': an end-of-match number for one player (needs player, no time_s). 'timeline': the Radiant-minus-Dire gold or xp advantage at a given minute (needs time_s, no player).")
    time_s: int | None = Field(default=None, description="Match time in seconds, only for kind=timeline; the curves have one value per minute, so use minute*60", multiple_of=60)
    metric: Metric = Field(description="For kind='stat': kills, deaths, assists, last_hits, gold_per_min, xp_per_min, net_worth, hero_damage, tower_damage. For kind='timeline': gold_adv or xp_adv.")
    value: int = Field(description="The number exactly as in the data: the player's end-of-match stat, or the Radiant-minus-Dire advantage at time_s (negative means Dire leads).")

    @model_validator(mode="after")
    def _check_kind(self):
        if self.kind == "stat":
            if self.player is None:
                raise ValueError(
                    "kind='stat' requires player as 'Hero (Team)', e.g. 'Drow Ranger (Radiant)'; none was given")
            if self.metric not in STAT_METRICS:
                raise ValueError(
                    f"kind='stat' needs a player stat metric ({', '.join(STAT_METRICS)}); "
                    f"got '{self.metric}'. Use kind='timeline' for gold_adv or xp_adv")
            if self.time_s is not None:
                raise ValueError(
                    "kind='stat' is an end-of-match number and must not have time_s; omit time_s")
        else:  # timeline
            if self.time_s is None:
                raise ValueError(
                    "kind='timeline' requires time_s, the minute * 60 (e.g. 720 for minute 12); none was given")
            if self.metric not in TIMELINE_METRICS:
                raise ValueError(
                    f"kind='timeline' needs metric gold_adv or xp_adv; got '{self.metric}'. "
                    "Use kind='stat' for player stats")
            if self.player is not None:
                raise ValueError(
                    "kind='timeline' is a team-level curve and must not have player; omit player")
        return self


class Finding(BaseModel):
    # # hypothesis_id is added in the agent systems; the baseline has no planner
    claim: str = Field(description="One falsifiable sentence about a specific player or team, e.g. 'Drow Ranger died 9 times while Radiant lost 3 towers.'")
    verdict: Verdict = Field(description="Whether the match data supports the hypothesis being investigated")
    severity: Severity = Field(description="How much this contributed to the result")
    evidence: list[Evidence] = Field(min_length=1, description="Facts from the match that support the claim")


class Report(BaseModel):
    answer: str = Field(description="Direct answer to the question, 2-4 sentences")
    turning_point_s: int | None = Field(default=None, description="Match time in seconds when the game swung; the data resolution is one minute. None if there was no clear swing")
    key_findings: list[Finding] = Field(description="The most important findings, most severe first")
    unresolved: list[str] = Field(default_factory=list, description="Open questions the data could not answer")


if __name__ == "__main__":
    import json
    print(json.dumps(Evidence.model_json_schema(), indent=1))
