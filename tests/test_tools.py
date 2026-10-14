import pytest

from coach.tools import ToolInputError, fetch_match
from coach.schemas import Evidence
from coach.tools import verify_claim


def test_fetch_match_returns_digest():
    text = fetch_match(9041878637)          # cached match, no network
    assert "WINNER: Dire" in text


def test_unparsed_match_raises_actionable_error(monkeypatch):
    monkeypatch.setattr("coach.tools.get_match", lambda _id: {})   # no "version" key
    with pytest.raises(ToolInputError, match="Do not retry"):
        fetch_match(123)


def test_verify_claim_ok():
    ev = Evidence(kind="stat", player="Tusk (Radiant)", metric="deaths", value=6)   # 1. build input
    result = verify_claim(9041878637, ev)                                          # 2. call
    assert result.startswith("OK")


def test_verify_claim_mismatch_names_the_right_minute():
    ev = Evidence(kind="timeline", metric="gold_adv", time_s=1320, value=-30596)
    result = verify_claim(9041878637, ev)
    assert "MISMATCH" in result
    assert "1260s" in result