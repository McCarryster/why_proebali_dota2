"""Timestamped events for one player: deaths, kills, purchases.

This is the information the digest deliberately leaves out. Output is a compact
text table, capped in size; errors are EventsInputError with a message the model
can act on (the tool layer turns it into a ToolInputError).
"""
from typing import Literal, get_args

from coach.dota.digest import _mmss, hero_names, npc_hero_labels, player_label

EventType = Literal["deaths", "kills", "purchases"]
EVENT_TYPES = get_args(EventType)

# Bought constantly and rarely matter for "what went wrong"; hidden to save tokens.
CONSUMABLES = {
    "tango", "branches", "flask", "clarity", "faerie_fire", "enchanted_mango", "ward_observer",
    "ward_sentry", "ward_dispenser", "smoke_of_deceit", "dust", "tpscroll", "quelling_blade",
    "blood_grenade", "cheese", "tome_of_knowledge",
}


class EventsInputError(ValueError):
    """The query cannot be answered as asked; the message says how to fix it."""


def player_events(match: dict, player: str, event_type: str, start_s: int = 0,
                  end_s: int | None = None, limit: int = 30,
                  heroes: dict[int, str] | None = None) -> str:
    heroes = heroes or hero_names()
    if event_type not in EVENT_TYPES:
        raise EventsInputError(f"Unknown event_type '{event_type}'. Use one of: {', '.join(EVENT_TYPES)}")
    by_label = {player_label(p, heroes): p for p in match["players"]}
    p = by_label.get(player)
    if p is None:
        raise EventsInputError(f"Unknown player '{player}'. Valid players: {', '.join(sorted(by_label))}")
    if end_s is not None and end_s <= start_s:
        raise EventsInputError(f"end_s ({end_s}) must be greater than start_s ({start_s})")

    npc = npc_hero_labels()
    team = {id(x): ("Radiant" if x["isRadiant"] else "Dire") for x in match["players"]}
    hero_team = {npc_key: team[id(x)] for x in match["players"]
                 for npc_key, name in npc.items() if name == heroes.get(x["hero_id"])}

    def who(key: str) -> str:
        if key in npc:
            return f"{npc[key]} ({hero_team.get(key, '?')})"
        return "tower/creep/neutral"  # non-hero killer (tower, creeps, fountain)

    rows = []  # (time, text)
    if event_type == "deaths":
        for d in p.get("deaths_log", []):
            rows.append((d["time"], f"killed by {who(d['key'])}, dead {d.get('time_dead', '?')}s"))
    elif event_type == "kills":
        for k in p.get("kills_log", []):
            rows.append((k["time"], f"killed {who(k['key'])}"))
    else:
        for b in p.get("purchase_log", []):
            if b["key"] not in CONSUMABLES:
                rows.append((b["time"], f"bought {b['key']}"))

    rows = [r for r in rows if r[0] >= start_s and (end_s is None or r[0] < end_s)]
    rows.sort(key=lambda r: r[0])
    window = f"{_mmss(start_s)}-{_mmss(end_s) if end_s is not None else 'end'}"
    if not rows:
        return f"{player} {event_type} {window}: none"
    shown = rows[:limit]
    out = [f"{player} {event_type} {window}: {len(rows)} event(s)"]
    out += [f"{_mmss(t)} ({t}s) {text}" for t, text in shown]   # seconds: copy into event evidence
    if len(rows) > limit:
        out.append(f"... {len(rows) - limit} more; narrow the window with start_s/end_s")
    return "\n".join(out)
