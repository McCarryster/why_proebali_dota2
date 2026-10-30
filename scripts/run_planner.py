import argparse
import asyncio
import uuid

from langfuse import get_client, propagate_attributes

from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.planner import make_plan


lf = get_client()            # AFTER the coach imports (they load .env)


DEFAULT_QUESTION = "What were the key mistakes?"


async def main(match_id: int, question: str):
    run_id = uuid.uuid4().hex[:8]
    with lf.start_as_current_observation(as_type="span", name="planner-run",
                                         input={"question": question, "match_id": match_id}) as root:
        with propagate_attributes(trace_name="planner-run",
                                  metadata={"system": "scratch", "match_id": str(match_id), "run_id": run_id}):
            async with McpTools() as tools:
                plan = await make_plan(question, match_id, tools)
            root.update(output={"hypotheses": [h.id for h in plan.hypotheses]})
            print("trace:", lf.get_trace_url())
            print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("match_id", type=int)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    args = parser.parse_args()
    asyncio.run(main(args.match_id, args.question))
    lf.flush()
