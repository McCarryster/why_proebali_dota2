"""Fetch one recent parsed match and print an inventory of what the API gives us."""
import sys
from pathlib import Path

from coach.dota import opendota

ids = opendota.recent_parsed_ids()
mid = ids[int(sys.argv[1]) if len(sys.argv) > 1 else 5]
m = opendota.get_match(mid)
print("match_id", mid, "| top-level keys:", len(m))
for k, v in m.items():
    if k == "players":
        continue
    desc = type(v).__name__
    if isinstance(v, (list, dict)):
        desc += f" len={len(v)}"
    else:
        desc += f" = {str(v)[:50]}"
    print(f"  {k}: {desc}")
p = m["players"][0]
print("\nplayer[0] keys:", len(p))
for k, v in p.items():
    desc = type(v).__name__
    if isinstance(v, (list, dict)):
        desc += f" len={len(v)}"
        if v and isinstance(v, list):
            desc += f" first={str(v[0])[:70]}"
    else:
        desc += f" = {str(v)[:40]}"
    print(f"  {k}: {desc}")
