"""Deterministic check of one Evidence item against real match data.

No LLM involved. This is the logic behind the `verify_claim` MCP tool and the
validator node. Messages are written for a model to read: they say what the
data actually is, so a retry can correct the *fact*, not just the format.
"""
from dataclasses import dataclass

from coach.dota.digest import hero_names, player_label
from coach.schemas import Evidence

# Evidence.metric -> key in OpenDota's player object
STAT_KEYS = {
    "kills": "kills", "deaths": "deaths", "assists": "assists", "last_hits": "last_hits",
    "gold_per_min": "gold_per_min", "xp_per_min": "xp_per_min", "net_worth": "net_worth",
    "hero_damage": "hero_damage", "tower_damage": "tower_damage",
}
CURVE_KEYS = {"gold_adv": "radiant_gold_adv", "xp_adv": "radiant_xp_adv"}


@dataclass
class VerifyResult:
    ok: bool
    message: str


def verify_evidence(match: dict, ev: Evidence, heroes: dict[int, str] | None = None) -> VerifyResult:
    heroes = heroes or hero_names()
    if ev.kind == "stat":
        return _verify_stat(match, ev, heroes)
    if ev.kind == "event":
        return _verify_event(match, ev, heroes)
    return _verify_timeline(match, ev)


def _verify_stat(match: dict, ev: Evidence, heroes: dict[int, str]) -> VerifyResult:
    by_label = {player_label(p, heroes): p for p in match["players"]}
    player = by_label.get(ev.player)
    if player is None:
        return VerifyResult(False, f"Unknown player '{ev.player}'. Valid players: "
                                   f"{', '.join(sorted(by_label))}")
    actual = player[STAT_KEYS[ev.metric]]
    if actual != ev.value:
        return VerifyResult(False, f"{ev.player} {ev.metric} is {actual}, not {ev.value}")
    return VerifyResult(True, f"{ev.player} {ev.metric} = {actual}")


def _verify_event(match: dict, ev: Evidence, heroes: dict[int, str]) -> VerifyResult:
    """A death/kill must exist in the player's log at exactly ev.time_s (seconds)."""
    by_label = {player_label(p, heroes): p for p in match["players"]}
    player = by_label.get(ev.player)
    if player is None:
        return VerifyResult(False, f"Unknown player '{ev.player}'. Valid players: "
                                   f"{', '.join(sorted(by_label))}")
    log = player.get("deaths_log" if ev.event_type == "deaths" else "kills_log", [])
    times = sorted(e["time"] for e in log)
    if ev.time_s in times:
        return VerifyResult(True, f"{ev.player} {ev.event_type} at {ev.time_s}s")
    msg = f"{ev.player} has no {ev.event_type[:-1]} at {ev.time_s}s"
    if times:
        shown = ", ".join(f"{t}s" for t in times[:10]) + (" ..." if len(times) > 10 else "")
        msg += f"; actual {ev.event_type} at: {shown}"
    else:
        msg += f"; this player has no {ev.event_type} at all"
    return VerifyResult(False, msg)


def _verify_timeline(match: dict, ev: Evidence) -> VerifyResult:
    curve = match[CURVE_KEYS[ev.metric]]
    minute = ev.time_s // 60
    if minute >= len(curve):
        return VerifyResult(False, f"No {ev.metric} data at {ev.time_s}s; the curve covers "
                                   f"0s to {(len(curve) - 1) * 60}s")
    actual = curve[minute]
    if actual == ev.value:
        return VerifyResult(True, f"{ev.metric} at {ev.time_s}s = {actual}")
    msg = f"{ev.metric} at {ev.time_s}s is {actual}, not {ev.value}"
    elsewhere = [m * 60 for m, v in enumerate(curve) if v == ev.value]
    if elsewhere:  # the off-by-one-minute mistake: the number is real, the time is wrong
        msg += f" ({ev.value} is the value at {elsewhere[0]}s)"
    return VerifyResult(False, msg)
