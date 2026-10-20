import urllib.error

from coach.dota.opendota import get_match
from coach.dota.digest import digest
from coach.dota.verify import verify_evidence
from coach.dota.events import EventType, EventsInputError, player_events
from coach.schemas import Evidence


MATCH_ID_DESC = "OpenDota match ID of a parsed match, e.g. 9041878637"
EVIDENCE_DESC = "The single fact to check: one player stat, or one gold/xp advantage value at a minute"
PLAYER_DESC = "Player label exactly as printed in the match digest: 'Hero (Team)', e.g. 'Dragon Knight (Radiant)'"
EVENT_TYPE_DESC = ("deaths: when the player died and who killed them; kills: heroes the player "
                   "killed; purchases: items bought (consumables like tango/wards are hidden)")
START_S_DESC = "Window start in seconds from match start, inclusive. 0 = start of the match"
END_S_DESC = "Window end in seconds, exclusive. Omit for the end of the match"

DESCRIPTIONS = {
    "fetch_match": "Start here. Returns a compact text digest of one finished Dota 2 match: result, "
            "per-player stats and final items, a per-minute gold/xp advantage table, building "
            "kills, and teamfight deaths per team. Use it once per match. Player labels in "
            "the form 'Hero (Team)' come from this digest and must be reused exactly.",
    "verify_claim": "Check one piece of evidence against the real match data before you cite it. "
            "Returns 'OK: ...' if it matches, or 'MISMATCH: ...' with the actual value; "
            "then correct the number or the time and check again. Read-only.",
    "get_events": "Time-stamped events for ONE player: deaths (with the killer), kills (with the "
            "victim) or non-consumable purchases. The digest only has totals; use this to learn "
            "WHEN something happened and by whom, e.g. what led up to a lost fight. Pass the player "
            "label exactly as in the digest. Results are capped at 30 rows; use start_s/end_s "
            "(seconds) to look at a window instead of the whole match. Read-only.",
}


class ToolInputError(Exception):
    """The model gave bad input; the message must tell it how to fix it."""


def _load_parsed_match(match_id: int) -> dict:
    # Infrastructure failures become tool errors with a next step. Not retried here: the
    # usual cause is an id OpenDota does not know, and a retry would just wait again.
    try:
        match_data = get_match(match_id)
    except urllib.error.HTTPError as e:     # must come before URLError (its parent class)
        raise ToolInputError(
            f"OpenDota returned HTTP {e.code} for match {match_id}; the id may not exist. "
            "Do not retry this match_id; tell the user.") from e
    except (TimeoutError, urllib.error.URLError) as e:
        raise ToolInputError(
            f"OpenDota did not answer for match {match_id} (timeout or network error); "
            "the id may not exist or the service is slow. Do not retry this match_id; "
            "tell the user.") from e
    if not match_data.get("version"):
        raise ToolInputError(
            f"Match {match_id} has no parsed replay data, so it cannot be analyzed "
            "(no timelines or events exist for it). Do not retry this match_id; "
            "tell the user it needs a parsed match.")
    return match_data


def fetch_match(match_id: int) -> str:
    return digest(_load_parsed_match(match_id))


def verify_claim(match_id: int, evidence: Evidence) -> str:
    # A mismatch is a normal answer to "is this true?", not bad input, so it is returned
    # as text instead of raised. Raising is for requests that cannot be answered at all
    # (e.g. an unparsed match); the model must be able to tell "your claim is false" from
    # "I could not check it".
    match_data = _load_parsed_match(match_id)
    verif_res = verify_evidence(match_data, evidence)

    if verif_res.ok:
        return f"OK: {verif_res.message}"
    return f"MISMATCH: {verif_res.message}"


def get_events(match_id: int, player: str, event_type: EventType,
               start_s: int = 0, end_s: int | None = None) -> str:
    match_data = _load_parsed_match(match_id)
    try:
        return player_events(match_data, player, event_type, start_s, end_s)
    except EventsInputError as e:
        raise ToolInputError(str(e)) from e