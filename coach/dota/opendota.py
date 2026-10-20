"""OpenDota client: disk-cached, rate-limit aware (free tier: 60/min, 3000/day)."""
import json
import time
import urllib.request
from pathlib import Path

BASE = "https://api.opendota.com/api"
TIMEOUT_S = 15  # OpenDota can hang on unknown ids; an agent should not wait a minute for that
RAW_DIR = Path(__file__).resolve().parents[2] / ".cache" / "opendota" / "matches"
_last_call = 0.0


def _get(path: str):
    global _last_call
    wait = 1.1 - (time.time() - _last_call)  # stay well under 60 calls/min
    if wait > 0:
        time.sleep(wait)
    _last_call = time.time()
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "dota-coach-learning"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read())


def get_match(match_id: int) -> dict:
    """Full match JSON, cached forever (finished matches never change, except
    that a parse can later add fields, so only cache once 'version' is set)."""
    path = RAW_DIR / f"{match_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    m = _get(f"/matches/{match_id}")
    if m.get("version"):  # present only when the replay has been parsed
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(m))
    return m


def recent_parsed_ids(less_than: int | None = None) -> list[int]:
    """~25 most recent parsed match ids; pass the smallest id seen to page back."""
    q = f"?less_than_match_id={less_than}" if less_than else ""
    return [x["match_id"] for x in _get("/parsedMatches" + q)]
