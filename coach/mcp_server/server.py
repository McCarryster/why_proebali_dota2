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
5. A claim about timing needs time-based evidence: for a death or kill use kind='event' with the exact seconds printed by get_events (e.g. 372 for 6:12); for a gold or xp swing use kind='timeline' (gold_adv or xp_adv at a minute, time_s = minute * 60). End-of-match stats cannot show when something happened.
6. Stop as soon as you have 2 to 3 verified pieces of evidence, or when the data cannot decide.

Finish by calling submit_finding with verdict supported, refuted or inconclusive. Use inconclusive when the evidence does not settle it.
"""


@mcp.prompt(description="Instructions for the planner: turn one question about one match into testable hypotheses.")
def planner(
    question: Annotated[str, Field(description="The question to answer, e.g. 'What were the key mistakes?'")],
    match_id: Annotated[int, Field(description=MATCH_ID_DESC)],
    avoid: Annotated[str, Field(description="Hypotheses already tested, one per line. Empty on the first round.")] = "",
) -> str:
    # Empty on the first round, so the first-round prompt stays byte-identical (cached model replies stay valid).
    already = f"\nAlready tested (do NOT repeat these or rephrase them):\n{avoid}\n" if avoid else ""
    return f"""\
You plan the investigation of Dota 2 match {match_id}. You will receive a compact overview of the match.

Question to answer: {question}
{already}
Propose 3 hypotheses (never more than 5) that could answer the question. Each one is later tested by a separate investigator who can only use these data:
- the overview you are given (end-of-match stats, per-minute gold and xp advantage, buildings destroyed, teamfights with deaths per team);
- timestamped deaths, kills and purchases of any single player.

Rules:
1. Each statement is ONE short sentence (at most 160 characters) naming ONE cause, with no numbers and no guesses ("likely", "probably"). Put the supporting numbers in the rationale.
2. Every hypothesis must be falsifiable with the data above. Do not propose things the data cannot show (positioning, drafts, communication, skill).
3. Make them about different causes (for example a fight, a player, the economy). Do not repeat the same idea in other words, and do not write hypotheses that depend on each other.
4. Prefer what the overview points at: a lopsided teamfight, the minute where the gold lead flips, a player with extreme stats.
5. Read the overview carefully: use the deaths per team shown for each teamfight to say who won it, and check a number before you rely on it.
6. Number them H1, H2, H3, most promising first, and give a rationale (one or two sentences) that names the evidence in the overview.

Finish by calling submit_plan.
"""


@mcp.prompt(description="Instructions for the report writer: turn verified findings into a short answer to the question.")
def reporter(
    question: Annotated[str, Field(description="The question to answer, e.g. 'What were the key mistakes?'")],
    match_id: Annotated[int, Field(description=MATCH_ID_DESC)],
) -> str:
    return f"""\
You write the final report for the investigation of Dota 2 match {match_id}.

Question to answer: {question}

You will receive the findings of the investigation. Every finding was already checked against the match data, and each shows its verdict (supported, refuted or inconclusive) and its severity. The findings are attached to the report automatically, so do not copy them.

Rules:
1. Answer the question directly in 2 to 4 sentences. Base the answer only on the findings you were given. Do not add facts, numbers or outside knowledge of the match.
2. A refuted finding is useful too: say what did NOT cause the result when it helps the answer.
3. Set turning_point_s only if a finding names a time (a death, a kill or a minute of the gold or xp curve) that marks the swing. Use that exact time in seconds. If no finding supports a turning point, leave it empty. Do not guess.
4. List in unresolved what the findings could not settle: every inconclusive finding, and every hypothesis that could not be tested. One short line each.

Finish by calling submit_report.
"""


if __name__ == "__main__":
    mcp.run(transport="stdio")