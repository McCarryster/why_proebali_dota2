from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from typing import Annotated
from pydantic import Field

from coach.tools import core as tools
from coach.tools.core import MATCH_ID_DESC, EVIDENCE_DESC, DESCRIPTIONS, PLAYER_DESC, EVENT_TYPE_DESC, START_S_DESC, END_S_DESC
from coach.schemas import Evidence
from coach.dota.events import EventType


mcp = MCPServer("dota-tools")


@mcp.tool(description=DESCRIPTIONS['fetch_match'])
def fetch_match(match_id: Annotated[int, Field(description=MATCH_ID_DESC)]) -> str:
    try:
        return tools.fetch_match(match_id)
    except tools.ToolInputError as e:
        raise ToolError(str(e)) from e # "from e" links the new exception to the original one so debugging traces show both the cause and the re-raised error


@mcp.tool(description=DESCRIPTIONS['verify_claim'])
def verify_claim(match_id: Annotated[int, Field(description=MATCH_ID_DESC)], evidence: Annotated[Evidence, Field(description=EVIDENCE_DESC)]) -> str:
    try:
        return tools.verify_claim(match_id, evidence)
    except tools.ToolInputError as e:
        raise ToolError(str(e)) from e


@mcp.tool(description=DESCRIPTIONS['get_events'])
def get_events(
    match_id: Annotated[int, Field(description=MATCH_ID_DESC)],
    player: Annotated[str, Field(description=PLAYER_DESC)],
    event_type: Annotated[EventType, Field(description=EVENT_TYPE_DESC)],
    start_s: Annotated[int, Field(description=START_S_DESC)] = 0,
    end_s: Annotated[int | None, Field(description=END_S_DESC)] = None,
) -> str:
    try:
        return tools.get_events(match_id, player, event_type, start_s, end_s)
    except tools.ToolInputError as e:
        raise ToolError(str(e)) from e


@mcp.prompt(description="Instructions for one investigator agent: one hypothesis, one match.")
def investigator(
    hypothesis: Annotated[str, Field(description="The single hypothesis to test, one sentence")],
    match_id: Annotated[int, Field(description=MATCH_ID_DESC)],
) -> str:
    return f"""\
You investigate ONE hypothesis about Dota 2 match {match_id}, using only the tools provided.

Hypothesis: {hypothesis}

How to work:
1. Call fetch_match first if you have not seen the digest. It has totals, curves, objectives and teamfights.
2. Use get_events to find WHEN things happened and by whom. Look at a time window, not the whole match.
3. Before you cite any number, check it with verify_claim. If it returns MISMATCH, use the actual value it gives you.
4. Cite only facts a tool returned. Do not guess or use outside knowledge of the match.
5. A claim about timing needs timeline evidence (gold_adv or xp_adv at a minute, time_s = minute * 60); end-of-match stats cannot show when something happened.
6. Stop as soon as you have 2 to 3 verified pieces of evidence, or when the data cannot decide.

Finish by calling submit_finding with verdict supported, refuted or inconclusive. Use inconclusive when the evidence does not settle it.
"""


if __name__ == "__main__":
    mcp.run(transport="stdio")