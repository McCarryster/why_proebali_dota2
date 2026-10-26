import argparse
import asyncio
import uuid

from langfuse import get_client, propagate_attributes

from coach.systems.scratch.investigator import run_investigator
from coach.systems.scratch.mcp_tools import McpTools


lf = get_client()


DEFAULT_HYPOTHESIS = "Radiant lost the teamfight at 10:41 and that flipped the game"


async def main(match_id: int, hypothesis: str):
    run_id = uuid.uuid4().hex[:8]
    with lf.start_as_current_observation(as_type="span", name="investigator-run",
                                            input={"hypothesis": hypothesis, "match_id": match_id}) as root:
        with propagate_attributes(trace_name="investigator-run",
                                  metadata={"system": "scratch", "match_id": str(match_id), "run_id": run_id}):
            async with McpTools() as tools:
                result = await run_investigator(hypothesis=hypothesis, match_id=match_id, tools=tools)
            root.update(output={"reason": result.reason, "tool_calls": result.tool_calls})
            print("trace:", lf.get_trace_url())
            print("reason:     ", result.reason)
            print("tool calls: ", result.tool_calls)
            if result.finding is not None:
                print(result.finding.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("match_id", type=int)
    parser.add_argument("--hypothesis", default=DEFAULT_HYPOTHESIS)
    args = parser.parse_args()
    asyncio.run(main(args.match_id, args.hypothesis))
    lf.flush()