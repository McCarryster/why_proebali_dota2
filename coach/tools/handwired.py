from pydantic import BaseModel, Field, ValidationError
from coach.schemas import Evidence
from coach.tools.core import fetch_match, verify_claim, get_events, ToolInputError, MATCH_ID_DESC, EVIDENCE_DESC, DESCRIPTIONS, PLAYER_DESC, EVENT_TYPE_DESC, START_S_DESC, END_S_DESC
from coach.dota.events import EventType


class FetchMatchArgs(BaseModel):
    match_id: int = Field(description=MATCH_ID_DESC)

class VerifyClaimArgs(BaseModel):
    match_id: int = Field(description=MATCH_ID_DESC)
    evidence: Evidence = Field(description=EVIDENCE_DESC)

class GetEventsArgs(BaseModel):
    match_id: int = Field(description=MATCH_ID_DESC)
    player: str = Field(description=PLAYER_DESC)
    event_type: EventType = Field(description=EVENT_TYPE_DESC)
    start_s: int = Field(default=0, description=START_S_DESC)
    end_s: int | None = Field(default=None, description=END_S_DESC)


REGISTRY = {
    "fetch_match": (FetchMatchArgs, fetch_match, DESCRIPTIONS["fetch_match"]),
    "verify_claim": (VerifyClaimArgs, verify_claim, DESCRIPTIONS["verify_claim"]),
    "get_events": (GetEventsArgs, get_events, DESCRIPTIONS["get_events"]),
}


def definitions(): # what you send to the API
    return [{"name": name, "description": desc, "input_schema": Args.model_json_schema()} for name, (Args, func, desc) in REGISTRY.items()]


def dispatch(name: str, args: dict): # when the model calls a tool
    # 1. unknown name -> check BEFORE looking it up
    if name not in REGISTRY:
        return (f"Unknown tool '{name}'. Available: {', '.join(REGISTRY)}", True)
    
    Args, func, desc = REGISTRY[name]   # look up by name
    
    # 2. arguments of the wrong shape
    try:
        parsed = Args.model_validate(args) # validate
    except ValidationError as e:
        lines = (f"- {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
        return ("Invalid arguments:\n" + "\n".join(lines), True)

    # 3. the function itself
    try:
        text = func(**dict(parsed))
    except ToolInputError as e:
        return (str(e), True)

    return (text, False) # success