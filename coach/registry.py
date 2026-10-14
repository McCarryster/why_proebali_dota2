from pydantic import BaseModel, Field
from coach.schemas import Evidence
from coach.tools import fetch_match, verify_claim


class FetchMatchArgs(BaseModel):
    match_id: int = Field(description="...")

class VerifyClaimArgs(BaseModel):
    match_id: int = Field(description="...")
    evidence: Evidence


REGISTRY = {
    "fetch_match": (FetchMatchArgs, fetch_match, "Use this first. Returns ..."),
    "verify_claim": (VerifyClaimArgs, verify_claim, "Use this to check ..."),
}


def definitions(): # what you send to the API
    return [{"name": name, "description": desc, "input_schema": Args.model_json_schema()} for name, (Args, func, desc) in REGISTRY.items()]

def dispatch(name, args): # when the model calls a tool
    Args, func, desc = REGISTRY[name]   # look up by name
    parsed = Args.model_validate(args)  # validate
    return func(**dict(parsed))  # run
