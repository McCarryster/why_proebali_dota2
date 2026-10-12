import json
import sys
from pathlib import Path

from coach.dota import opendota
from coach.dota.digest import digest

mid = int(sys.argv[1]) if len(sys.argv) > 1 else json.loads(
    (Path(__file__).resolve().parent.parent / "data" / "matches.json").read_text())[2]["match_id"]
text = digest(opendota.get_match(mid))
print(text)
print(f"\n[{len(text)} chars, ~{len(text) // 4} tokens]")
