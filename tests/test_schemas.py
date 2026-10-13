import pytest
from pydantic import ValidationError

from coach.schemas import Evidence, Finding, Report


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


def test_time_must_be_whole_minute():
    with pytest.raises(ValidationError) as exc:
        Evidence(kind="timeline", metric="gold_adv", time_s=725, value=-1)
    assert error_locs(exc) == [("time_s",)]
