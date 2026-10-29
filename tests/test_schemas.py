import pytest
from pydantic import ValidationError

from coach.schemas import Evidence, Finding, Hypothesis, Plan, Report


def make_evidence(**overrides):
    fields = dict(kind="stat", player="Drow Ranger (Radiant)", metric="deaths", value=9)
    return Evidence(**{**fields, **overrides})


def make_finding_fields(**overrides):
    fields = dict(
        claim="Drow Ranger died 9 times while Radiant lost 3 towers.",
        verdict="supported",
        severity="major",
        evidence=[make_evidence()],
    )
    return {**fields, **overrides}


def error_locs(exc_info):
    """Which fields the validation error points at, e.g. [('metric',)]."""
    return [e["loc"] for e in exc_info.value.errors()]


def test_valid_report():
    report = Report(
        answer="Radiant lost the mid game.",
        key_findings=[Finding(**make_finding_fields())],
    )
    assert report.key_findings[0].evidence[0].value == 9
    assert report.turning_point_s is None
    assert report.unresolved == []


def test_finding_needs_evidence():
    # Only `evidence` differs from the valid finding, so this fails for that reason alone.
    with pytest.raises(ValidationError) as exc:
        Finding(**make_finding_fields(evidence=[]))
    assert error_locs(exc) == [("evidence",)]


def test_bad_metric_rejected():
    with pytest.raises(ValidationError) as exc:
        make_evidence(metric="KDA")
    assert error_locs(exc) == [("metric",)]


def test_valid_timeline_evidence():
    e = Evidence(kind="timeline", metric="gold_adv", time_s=720, value=-2334)
    assert e.player is None


@pytest.mark.parametrize("overrides, why", [
    (dict(player=None), "stat needs player"),
    (dict(metric="gold_adv"), "stat can't use a timeline metric"),
    (dict(time_s=720), "stat must not have time_s"),
])
def test_stat_rules(overrides, why):
    with pytest.raises(ValidationError, match="kind='stat'"):
        make_evidence(**overrides)


@pytest.mark.parametrize("fields, why", [
    (dict(metric="gold_adv", value=-1), "timeline needs time_s"),
    (dict(metric="deaths", time_s=720, value=-1), "timeline can't use a stat metric"),
    (dict(metric="gold_adv", time_s=720, player="Tusk (Radiant)", value=-1),
     "timeline must not have player"),
])
def test_timeline_rules(fields, why):
    with pytest.raises(ValidationError, match="kind='timeline'"):
        Evidence(kind="timeline", **fields)


def test_timeline_time_must_be_a_whole_minute():
    # The rule lives in the model validator now (event times are exact seconds), so the error is model-level.
    with pytest.raises(ValidationError, match="multiple of 60"):
        Evidence(kind="timeline", metric="gold_adv", time_s=725, value=-1)


def test_valid_event_evidence():
    e = Evidence(kind="event", player="Dragon Knight (Radiant)", event_type="deaths", time_s=372)
    assert e.metric is None and e.value is None


def test_event_time_is_an_exact_second_not_a_minute():
    Evidence(kind="event", player="Dragon Knight (Radiant)", event_type="deaths", time_s=373)  # no error


@pytest.mark.parametrize("fields, fragment", [
    (dict(event_type="deaths", time_s=372), "requires player"),
    (dict(player="Dragon Knight (Radiant)", time_s=372), "requires event_type"),
    (dict(player="Dragon Knight (Radiant)", event_type="deaths"), "requires time_s"),
    (dict(player="Dragon Knight (Radiant)", event_type="deaths", time_s=372, value=9), "must not have value"),
    (dict(player="Dragon Knight (Radiant)", event_type="deaths", time_s=372, metric="deaths"), "must not have metric"),
])
def test_event_rules(fields, fragment):
    with pytest.raises(ValidationError, match=fragment):
        Evidence(kind="event", **fields)


def test_stat_must_not_carry_event_fields():
    with pytest.raises(ValidationError, match="must not have event_type"):
        make_evidence(event_type="deaths")


def test_a_valid_stat_still_passes():
    # Regression: an earlier draft compared the player against the metrics list and rejected every stat.
    assert make_evidence().player == "Drow Ranger (Radiant)"


def test_timeline_must_not_carry_a_player():
    with pytest.raises(ValidationError, match="must not have player"):
        Evidence(kind="timeline", metric="gold_adv", time_s=720, value=-1, player="Tusk (Radiant)")


def hyp(id="H1"):
    return dict(id=id, statement="Radiant lost a big fight.", rationale="The digest shows a 5-0 fight at 10:41.")


def test_valid_plan():
    plan = Plan(hypotheses=[hyp("H1"), hyp("H2")])
    assert [h.id for h in plan.hypotheses] == ["H1", "H2"]


def test_duplicate_hypothesis_ids_are_rejected_and_named():
    with pytest.raises(ValidationError, match="repeated: H1"):
        Plan(hypotheses=[hyp("H1"), hyp("H1")])


@pytest.mark.parametrize("bad_id", ["1", "h1", "Hypothesis 1", "H", "H1a"])
def test_hypothesis_id_must_look_like_h_and_digits(bad_id):
    with pytest.raises(ValidationError) as exc:
        Hypothesis(**hyp(bad_id))
    assert [e["loc"] for e in exc.value.errors()] == [("id",)]


def test_plan_size_limits():
    with pytest.raises(ValidationError):
        Plan(hypotheses=[])
    with pytest.raises(ValidationError):
        Plan(hypotheses=[hyp(f"H{i}") for i in range(1, 7)])      # six: one too many


def test_hypothesis_statement_is_limited_to_160_characters():
    ok = dict(hyp("H1"), statement="x" * 160)
    Hypothesis(**ok)                                              # exactly at the limit: fine
    with pytest.raises(ValidationError) as exc:
        Hypothesis(**dict(ok, statement="x" * 161))
    assert [e["loc"] for e in exc.value.errors()] == [("statement",)]


# Seen in a real run: the model's tool-call markup leaked into the claim and swallowed the verdict.
LEAKED_CLAIM = ("Tusk still bought blink at 9:17 and Scepter at 15:09."
                "</claim>\n<parameter name=\"verdict\">refuted")


def test_claim_with_leaked_markup_is_rejected_and_the_claim_is_named():
    fields = make_finding_fields(claim=LEAKED_CLAIM)
    del fields["verdict"]                       # the real failure: markup swallowed the verdict
    with pytest.raises(ValidationError) as exc:
        Finding(**fields)
    locs = error_locs(exc)
    assert ("claim",) in locs                   # the fact the model needs to see
    assert ("verdict",) in locs


@pytest.mark.parametrize("claim", [
    "Dragon Knight died 9 times, fewer than Drow Ranger's 12.",
    "Radiant had < 5 towers left and deaths <5 per player were rare.",
    "Gold lead went from +3012 at 11:00 to -2334 at 12:00 (a 5346 swing).",
])
def test_ordinary_claims_are_not_mistaken_for_markup(claim):
    assert Finding(**make_finding_fields(claim=claim)).claim == claim
