"""Pick 10 ordinary, fully-parsed matches and record them in data/matches.json.

Criteria are fixed up front (so the pick is not tuned to a model's output):
  - parsed (version set), 10 human players, no leavers/abandons
  - game_mode 23 (Turbo: short matches, cheaper runs), lobby_type 0 or 7
  - duration 18-35 min  -> enough minutes of gold/xp curves to have a turning point
  - per-minute advantage curves present for the whole match
  - not a pro/league match (leagueid == 0)  -> low contamination risk
  - mix: at least 4 'comebacks' (the winner trailed in gold by >= 4000 at some point; Turbo gold flows faster)
"""
import json
import sys
from pathlib import Path

from coach.dota import opendota

TARGET, MIN_COMEBACKS, MAX_CANDIDATES = 10, 4, 120


def summarize(m):
    gold = m["radiant_gold_adv"]
    sign = 1 if m["radiant_win"] else -1
    winner_gold = [g * sign for g in gold]  # >0 means the eventual winner leads
    return {
        "match_id": m["match_id"], "duration_s": m["duration"], "radiant_win": m["radiant_win"],
        "game_mode": m["game_mode"], "min_winner_gold_adv": min(winner_gold),
        "max_abs_gold_adv": max(abs(g) for g in gold),
        "comeback": min(winner_gold) <= -4000,
    }


def ok(m):
    if not m.get("version") or m.get("leagueid") or m.get("human_players") != 10:
        return False
    if m.get("game_mode") != 23 or m.get("lobby_type") not in (0, 7):
        return False
    if not 18 * 60 <= m["duration"] <= 35 * 60:
        return False
    gold = m.get("radiant_gold_adv") or []
    if len(gold) < m["duration"] // 60:
        return False
    if any(p.get("leaver_status") or p.get("abandons") for p in m["players"]):
        return False
    return all(p.get("purchase_log") and p.get("gold_t") for p in m["players"])


picked, comebacks, seen, less_than = [], 0, 0, None
while len(picked) < TARGET and seen < MAX_CANDIDATES:
    ids = opendota.recent_parsed_ids(less_than)
    less_than = min(ids)
    for mid in ids:
        seen += 1
        m = opendota.get_match(mid)
        if not ok(m):
            continue
        s = summarize(m)
        # reserve slots so we still reach MIN_COMEBACKS
        slots_left = TARGET - len(picked)
        if not s["comeback"] and slots_left <= MIN_COMEBACKS - comebacks:
            continue
        picked.append(s)
        comebacks += s["comeback"]
        print(f"picked {len(picked):2d}: {s}")
        if len(picked) == TARGET:
            break

out = Path(__file__).resolve().parent.parent / "data" / "matches.json"
out.write_text(json.dumps(picked, indent=1))
print(f"\n{len(picked)} matches, {comebacks} comebacks, {seen} candidates inspected -> {out}")
