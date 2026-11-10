import sys
import asyncio
import uuid
from dotenv import load_dotenv

from langfuse.langchain import CallbackHandler
from langfuse import get_client, propagate_attributes

from langchain.mcp import MCPAdapter
from langchain_anthropic import ChatAnthropic

from coach.systems.langgraph.investigator import run_investigator


load_dotenv()


lf = get_client()


model_name = "claude-haiku-5-5"

MAX_TOOL_CALLS = 8
MAX_ATTEMPTS = 2


config = {
    "mcpServers": {
        "dota-tools": {"command": sys.executable, "args": ["-m", "coach.mcp_server.server"]},
    }
}
print("-"*50)


async def main(hypothesis: str, match_id: str):
    run_id = uuid.uuid4().hex[:8]
    with lf.start_as_current_observation(input={"hypothesis": hypothesis, "match_id": match_id}, 
                                         as_type="span", name="investigate") as root:
        with propagate_attributes(trace_name="investigate",
                                  metadata={"system": "langgraph", "match_id": str(match_id), "run_id": run_id}):
            async with MCPAdapter(config) as adapter:
                prompt = await adapter.client.get_prompt("investigator", {"hypothesis": hypothesis, "match_id": str(match_id)}) # type: ignore
                prompt_text = prompt.messages[0].content.text # type: ignore
                
                tools = await adapter.list_tools()

                model = ChatAnthropic(
                    model_name=model_name,
                    max_tokens_to_sample=3000,
                    output_config={"effort": "low"},
                    timeout=60,
                    stop=None
                )

                handler = CallbackHandler()

                result = await run_investigator(
                    match_id=match_id, tools=tools, model=model,
                    prompt_text=prompt_text, config={"callbacks": [handler]},
                    max_tool_calls=MAX_TOOL_CALLS, max_attempts=MAX_ATTEMPTS
                )

                print(f"reason = {result.reason} | tool_calls = {result.tool_calls} | tokens = {result.tokens}")
                print(f"finding = {result.finding}")

                root.update(output={"reason": result.reason,
                                    "tokens": result.tokens,
                                    "tool_calls_requested": result.tool_calls,
                                    "finding": result.finding.model_dump() if result.finding else None,
                                    })
                print("trace:", lf.get_trace_url())
                lf.flush()

match_id = "9041884546"
hypothesis = "The Radiant lost its lead because of repeated deaths before the 15 minute mark"
asyncio.run(main(hypothesis, match_id)) 