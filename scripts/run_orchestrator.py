import argparse
import asyncio
import uuid

from langfuse import get_client, propagate_attributes

from coach.systems.scratch.mcp_tools import McpTools
from coach.systems.scratch.orchestrator import run_orchestrator


lf = get_client()


DEFAULT_QUESTION = "What were the key mistakes?"


async def main(match_id: int, question: str):
    run_id = uuid.uuid4().hex[:8]
    with lf.start_as_current_observation(as_type="span", name="orchestrator-run",
                                         input={"question": question, "match_id": match_id}) as root:
        with propagate_attributes(trace_name="orchestrator-run",
                                  metadata={"system": "scratch", "match_id": str(match_id), "run_id": run_id}):
            async with McpTools() as tools:
                result = await run_orchestrator(question, match_id, tools)
            root.update(output={
                "answer": result.report.answer,
                "turning_point_s": result.report.turning_point_s,
                "findings": len(result.report.key_findings),
                "dropped": result.state.dropped,
                "iterations": result.state.iteration+1,
                "tokens_spent": result.state.tokens_spent,
            })
            print("trace:", lf.get_trace_url())
            print(result.report.model_dump_json(indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("match_id", type=int)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    args = parser.parse_args()
    asyncio.run(main(args.match_id, args.question))
    lf.flush()
