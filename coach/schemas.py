import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


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




# Fields that must be absent for each kind of evidence (the required ones are checked below).
FORBIDDEN_FIELDS = {
    "stat": ("time_s", "event_type"),
    "timeline": ("player", "event_type"),
    "event": ("metric", "value"),
}


class Evidence(BaseModel):
    kind: Literal["stat", "timeline", "event"] = Field(
        description="'stat': an end-of-match number for one player (needs player, metric, value). "
                    "'timeline': the Radiant-minus-Dire gold or xp advantage at a minute "
                    "(needs metric, time_s, value). 'event': one death or kill of a player at an exact "
                    "second (needs player, event_type, time_s).")
    player: str | None = Field(
        default=None,
        description="Player label exactly as in the match digest: 'Hero (Team)', e.g. 'Drow Ranger (Radiant)'. "
                    "For kind='stat' and kind='event'; omit for kind='timeline'.")
    event_type: Literal["deaths", "kills"] | None = Field(
        default=None,
        description="Only for kind='event'. 'deaths': the player died at time_s. 'kills': the player killed "
                    "a hero at time_s. Take both from the get_events output.")
    time_s: int | None = Field(
        default=None, ge=0,
        description="Seconds from match start. kind='timeline': minute * 60 (the curves have one value per "
                    "minute). kind='event': the exact second shown in get_events, e.g. 372 for 6:12. "
                    "Omit for kind='stat'.")
    metric: Metric | None = Field(
        default=None,
        description="For kind='stat': kills, deaths, assists, last_hits, gold_per_min, xp_per_min, net_worth, "
                    "hero_damage, tower_damage. For kind='timeline': gold_adv or xp_adv. Omit for kind='event'.")
    value: int | None = Field(
        default=None,
        description="The number exactly as in the data: the player's end-of-match stat, or the "
                    "Radiant-minus-Dire advantage at time_s (negative means Dire leads). Omit for kind='event'.")

    @model_validator(mode="after")
    def _check_kind(self):
        if self.kind == "stat":
            if self.player is None:
                raise ValueError("kind='stat' requires player as 'Hero (Team)', e.g. 'Drow Ranger (Radiant)'; none was given")
            if self.metric not in STAT_METRICS:
                raise ValueError(
                    f"kind='stat' needs a player stat metric ({', '.join(STAT_METRICS)}); "
                    f"got '{self.metric}'. Use kind='timeline' for gold_adv or xp_adv")
            if self.value is None:
                raise ValueError("kind='stat' requires value, the number from the PLAYERS table; none was given")

        if self.kind == "timeline":
            if self.time_s is None:
                raise ValueError("kind='timeline' requires time_s, the minute * 60 (e.g. 720 for minute 12); none was given")
            if self.time_s % 60 != 0:
                raise ValueError(
                    f"kind='timeline' needs time_s to be a multiple of 60 (minute * 60, e.g. 720 for minute 12); got {self.time_s}")
            if self.metric not in TIMELINE_METRICS:
                raise ValueError(
                    f"kind='timeline' needs metric gold_adv or xp_adv; got '{self.metric}'. Use kind='stat' for player stats")
            if self.value is None:
                raise ValueError("kind='timeline' requires value, the advantage from the curves table; none was given")

        if self.kind == "event":
            if self.player is None:
                raise ValueError("kind='event' requires player as 'Hero (Team)', e.g. 'Dragon Knight (Radiant)'; none was given")
            if self.event_type is None:
                raise ValueError("kind='event' requires event_type, 'deaths' or 'kills'; none was given")
            if self.time_s is None:
                raise ValueError("kind='event' requires time_s, the exact second from get_events (e.g. 372 for 6:12); none was given")
        
        extra = [name for name in FORBIDDEN_FIELDS[self.kind] if getattr(self, name) is not None]
        if extra:
            raise ValueError(f"kind='{self.kind}' must not have {', '.join(extra)}; omit {'it' if len(extra) == 1 else 'them'}")
        return self


class Finding(BaseModel):
    # # hypothesis_id is added in the agent systems; the baseline has no planner
    claim: str = Field(description="One falsifiable sentence about a specific player or team, e.g. 'Drow Ranger died 9 times while Radiant lost 3 towers.'")
    verdict: Verdict = Field(description="Whether the match data supports the hypothesis being investigated")
    severity: Severity = Field(description="How much this contributed to the result")
    evidence: list[Evidence] = Field(min_length=1, description="Facts from the match that support the claim")

    @field_validator("claim")
    @classmethod
    def _claim_is_plain_text(cls, claim: str) -> str:
        # Seen in a real run: the model's tool-call markup ('</claim>', '<parameter name="verdict">')
        # leaked into this string and swallowed the verdict. Say so, or the retry repeats the mistake.
        # The pattern needs a letter after '<', so ordinary text like 'deaths < 5' passes.
        if re.search(r"</?[A-Za-z]", claim):
            raise ValueError("claim must be plain text but contains markup such as '</claim>' or '<parameter'. "
                             "Write only the claim sentence here and put the verdict in the separate 'verdict' field")
        return claim


class ReportDraft(BaseModel):
    answer: str = Field(description="Direct answer to the question, 2-4 sentences")
    turning_point_s: int | None = Field(default=None, description="Match time in seconds when the game swung; the data resolution is one minute. None if there was no clear swing")
    unresolved: list[str] = Field(default_factory=list, description="Open questions the data could not answer")


class Report(ReportDraft):
    key_findings: list[Finding] = Field(description="The most important findings, most severe first")


class Hypothesis(BaseModel):
    id: str = Field(pattern=r"^H\d+$", description="Short unique id: 'H1', 'H2', 'H3', ... numbered in order, no repeats.")
    statement: str = Field(
        max_length=160,
        description="ONE short falsifiable sentence naming ONE cause, at most 160 characters, no numbers and no "
                    "guesses, e.g. 'Dragon Knight kept dying before minute 11, weakening Radiant before the 10:41 "
                    "fight.' Put the supporting numbers in the rationale.")
    rationale: str = Field(description="One sentence on why this is worth testing, pointing at what in the match overview suggests it.")


class Plan(BaseModel):
    hypotheses: list[Hypothesis] = Field(
        min_length=1, max_length=5,
        description="1 to 5 distinct hypotheses that could explain the result or the key mistakes, "
                    "most promising first. Each is investigated separately, so make them independent.")

    @model_validator(mode="after")
    def _unique_ids(self):
        ids = [h.id for h in self.hypotheses]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(
                f"hypothesis ids must be unique; repeated: {', '.join(dupes)}. "
                "Number them H1, H2, H3, ... once each")
        return self


if __name__ == "__main__":
    import json
    print(json.dumps(Evidence.model_json_schema(), indent=1))
