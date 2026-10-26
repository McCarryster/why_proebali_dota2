import pytest

from coach.dota.verify import verify_evidence
from coach.schemas import Evidence

HEROES = {1: "Drow Ranger", 2: "Tusk"}
MATCH = {
    "players": [
        {"hero_id": 1, "isRadiant": True, "deaths": 9, "kills": 9, "assists": 9, "last_hits": 69,
         "gold_per_min": 972, "xp_per_min": 1479, "net_worth": 21720, "hero_damage": 25013,
         "tower_damage": 4944},
        {"hero_id": 2, "isRadiant": False, "deaths": 6, "kills": 2, "assists": 10, "last_hits": 17,
         "gold_per_min": 543, "xp_per_min": 1498, "net_worth": 11212, "hero_damage": 12244,
         "tower_damage": 0},
    ],
    "radiant_gold_adv": [0, 100, -50, 300],
    "radiant_xp_adv": [0, 10, 20, 30],
}


def stat(player="Drow Ranger (Radiant)", metric="deaths", value=9):
    return Evidence(kind="stat", player=player, metric=metric, value=value)


def timeline(time_s, value, metric="gold_adv"):
    return Evidence(kind="timeline", metric=metric, time_s=time_s, value=value)


def check(ev):
    return verify_evidence(MATCH, ev, HEROES)


def test_correct_stat():
    assert check(stat()).ok


def test_wrong_stat_reports_actual_value():
    r = check(stat(value=7))
    assert not r.ok
    assert "is 9, not 7" in r.message


def test_unknown_player_lists_valid_players():
    r = check(stat(player="Drow (Radiant)"))
    assert not r.ok
    assert "Drow Ranger (Radiant)" in r.message and "Tusk (Dire)" in r.message


def test_same_hero_wrong_team_is_unknown():
    assert not check(stat(player="Tusk (Radiant)")).ok


def test_correct_timeline():
    assert check(timeline(120, -50)).ok


def test_wrong_timeline_hints_at_the_minute_where_value_is_true():
    r = check(timeline(180, 100))     # 100 is the value at 60 s, not at 180 s
    assert not r.ok
    assert "is 300, not 100" in r.message
    assert "value at 60s" in r.message


def test_time_beyond_curve():
    r = check(timeline(600, 0))
    assert not r.ok
    assert "covers 0s to 180s" in r.message


@pytest.mark.parametrize("metric", ["kills", "deaths", "assists", "last_hits", "gold_per_min",
                                    "xp_per_min", "net_worth", "hero_damage", "tower_damage"])
def test_every_stat_metric_is_looked_up(metric):
    actual = MATCH["players"][0][metric]
    assert check(stat(metric=metric, value=actual)).ok


def event(time_s, event_type="deaths", player="Drow Ranger (Radiant)"):
    return Evidence(kind="event", player=player, event_type=event_type, time_s=time_s)


MATCH_WITH_EVENTS = {
    "players": [dict(MATCH["players"][0],
                     deaths_log=[{"time": 100, "key": "npc_dota_hero_tusk"}, {"time": 300, "key": "x"}],
                     kills_log=[{"time": 250, "key": "npc_dota_hero_tusk"}]),
                MATCH["players"][1]],
    "radiant_gold_adv": MATCH["radiant_gold_adv"], "radiant_xp_adv": MATCH["radiant_xp_adv"],
}


def test_event_exact_second_is_ok():
    assert verify_evidence(MATCH_WITH_EVENTS, event(100), HEROES).ok
    assert verify_evidence(MATCH_WITH_EVENTS, event(250, "kills"), HEROES).ok


def test_event_wrong_second_lists_the_real_ones():
    r = verify_evidence(MATCH_WITH_EVENTS, event(101), HEROES)
    assert not r.ok
    assert "no death at 101s" in r.message and "100s, 300s" in r.message


def test_event_for_player_without_such_events():
    r = verify_evidence(MATCH_WITH_EVENTS, event(100, player="Tusk (Dire)"), HEROES)
    assert not r.ok and "no deaths at all" in r.message


def test_event_unknown_player_lists_valid_players():
    r = verify_evidence(MATCH_WITH_EVENTS, event(100, player="Drow (Radiant)"), HEROES)
    assert not r.ok and "Valid players" in r.message
