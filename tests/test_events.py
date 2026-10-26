import pytest

from coach.dota.events import EventsInputError, player_events

HEROES = {1: "Drow Ranger", 2: "Tusk"}
MATCH = {"players": [
    {"hero_id": 1, "isRadiant": True,
     "deaths_log": [{"time": 100, "key": "npc_dota_hero_tusk", "time_dead": 15},
                    {"time": 300, "key": "npc_dota_badguys_tower1_mid", "time_dead": 20}],
     "kills_log": [{"time": 250, "key": "npc_dota_hero_tusk"}],
     "purchase_log": [{"time": -59, "key": "tango"}, {"time": 400, "key": "manta"}]},
    {"hero_id": 2, "isRadiant": False, "deaths_log": [], "kills_log": [], "purchase_log": []},
]}
NPC = {"npc_dota_hero_drow_ranger": "Drow Ranger", "npc_dota_hero_tusk": "Tusk"}


@pytest.fixture(autouse=True)
def fake_npc_names(monkeypatch):
    monkeypatch.setattr("coach.dota.events.npc_hero_labels", lambda: NPC)


def q(event_type, **kw):
    return player_events(MATCH, "Drow Ranger (Radiant)", event_type, heroes=HEROES, **kw)


def test_deaths_name_the_killer_with_team():
    text = q("deaths")
    assert "1:40 (100s) killed by Tusk (Dire)" in text
    assert "5:00 (300s) killed by tower/creep/neutral" in text


def test_window_is_start_inclusive_end_exclusive():
    assert "none" in q("deaths", start_s=101, end_s=300)
    assert "5:00" in q("deaths", start_s=300)


def test_consumables_are_hidden_from_purchases():
    text = q("purchases")
    assert "manta" in text and "tango" not in text


def test_row_cap_says_how_to_narrow():
    many = {"players": [dict(MATCH["players"][0],
                             purchase_log=[{"time": i, "key": f"item{i}"} for i in range(50)]),
                        MATCH["players"][1]]}
    text = player_events(many, "Drow Ranger (Radiant)", "purchases", limit=5, heroes=HEROES)
    assert "45 more" in text and "start_s/end_s" in text


@pytest.mark.parametrize("kwargs, fragment", [
    (dict(player="Drow (Radiant)", event_type="deaths"), "Valid players"),
    (dict(player="Drow Ranger (Radiant)", event_type="deaths_total"), "Use one of"),
    (dict(player="Drow Ranger (Radiant)", event_type="deaths", start_s=60, end_s=30), "greater than start_s"),
])
def test_bad_input_messages_say_what_to_do(kwargs, fragment):
    with pytest.raises(EventsInputError, match=fragment):
        player_events(MATCH, heroes=HEROES, **kwargs)
