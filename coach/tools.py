from coach.dota.opendota import get_match
from coach.dota.digest import digest
from coach.dota.verify import verify_evidence
from coach.schemas import Evidence


class ToolInputError(Exception):
    """The model gave bad input; the message must tell it how to fix it."""


def _load_parsed_match(match_id: int) -> dict:
    match_data = get_match(match_id)
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