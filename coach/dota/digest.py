"""Compact text digest of a match (~2-3k tokens).

This is the shared starting point: the baseline gets exactly this text and the
agents' `fetch_match` tool will return exactly this text. Whitelist, not
blacklist: only fields named here ever reach a model, so leakage fields like
`throw` / `loss` (OpenDota's own comeback scores) cannot slip through.

Players are named by hero (unique within a match), e.g. "Rubick (Dire)".
"""
import json
from pathlib import Path

from coach.dota.opendota import _get

CONST_DIR = Path(__file__).resolve().parents[2] / ".cache" / "opendota" / "constants"


def _constant(name: str, path: str):
    f = CONST_DIR / f"{name}.json"
    if not f.exists():
        CONST_DIR.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(_get(path)))
    return json.loads(f.read_text())


def hero_names() -> dict[int, str]:
    return {h["id"]: h["localized_name"] for h in _constant("heroes", "/heroes")}


def item_names() -> dict[int, str]:
    return {int(k): v for k, v in _constant("item_ids", "/constants/item_ids").items()}


def player_label(p: dict, heroes: dict[int, str]) -> str:
    return f"{heroes.get(p['hero_id'], p['hero_id'])} ({'Radiant' if p['isRadiant'] else 'Dire'})"


def _mmss(s: int) -> str:
    sign = "-" if s < 0 else ""
    s = abs(s)
    return f"{sign}{s // 60}:{s % 60:02d}"


def _building(key: str) -> str:
    """npc_dota_goodguys_tower1_mid -> 'Radiant tower1 mid'."""
    team = "Radiant" if "goodguys" in key else "Dire"
    parts = key.replace("npc_dota_", "").split("_")[1:]
    return f"{team} {' '.join(parts)}"


def digest(m: dict) -> str:
    heroes, items = hero_names(), item_names()
    winner = "Radiant" if m["radiant_win"] else "Dire"
    lines = [
        f"MATCH {m['match_id']} | Turbo | duration {_mmss(m['duration'])} | WINNER: {winner}"
        f" | final kills Radiant {m['radiant_score']} - Dire {m['dire_score']}",
        "",
        "PLAYERS (pos = estimated role 1-5; NW = net worth; TFP = teamfight participation)",
        "team    pos hero                 K/D/A     LH   GPM  XPM    NW  HeroDmg TowerDmg TFP  final items",
    ]
    for p in sorted(m["players"], key=lambda p: (not p["isRadiant"], p.get("position_est") or 9)):
        its = [items.get(p[f"item_{i}"], "?") for i in range(6) if p.get(f"item_{i}")]
        lines.append(
            f"{'Radiant' if p['isRadiant'] else 'Dire':7} {p.get('position_est') or '?':>3} "
            f"{heroes.get(p['hero_id'], '?'):20} {p['kills']:>2}/{p['deaths']:>2}/{p['assists']:>2} "
            f"{p['last_hits']:>5} {p['gold_per_min']:>5} {p['xp_per_min']:>4} {p['net_worth']:>6} "
            f"{p['hero_damage']:>8} {p['tower_damage']:>8} {p.get('teamfight_participation') or 0:.2f} "
            f"{', '.join(its)}")

    gold, xp = m["radiant_gold_adv"], m["radiant_xp_adv"]
    lines += ["", "ADVANTAGE CURVES, Radiant minus Dire, one value per minute starting at minute 0",
              "gold_adv: " + " ".join(str(g) for g in gold),
              "xp_adv:   " + " ".join(str(x) for x in xp)]

    lines += ["", "OBJECTIVES (time mm:ss, killer -> what)"]
    by_slot = {p["player_slot"]: player_label(p, heroes) for p in m["players"]}
    for o in sorted(m["objectives"], key=lambda o: o["time"]):
        who = by_slot.get(o.get("player_slot"), "creeps/unknown")
        if o["type"] == "CHAT_MESSAGE_FIRSTBLOOD":
            lines.append(f"{_mmss(o['time'])} first blood: {who} killed "
                         f"{by_slot.get(o.get('victim_player_slot'), '?')}")
        elif o["type"] == "building_kill":
            lines.append(f"{_mmss(o['time'])} {who} destroyed {_building(o['key'])}")

    lines += ["", "TEAMFIGHTS (start-end | deaths per team)"]
    for t in m["teamfights"]:
        # t["players"] is in the same order as m["players"]
        dead = {"Radiant": 0, "Dire": 0}
        for p, tp in zip(m["players"], t["players"]):
            dead["Radiant" if p["isRadiant"] else "Dire"] += tp["deaths"]
        lines.append(f"{_mmss(t['start'])}-{_mmss(t['end'])} | deaths: "
                     f"Radiant {dead['Radiant']}, Dire {dead['Dire']}")
    return "\n".join(lines)
