import sys
import asyncio
import uuid
from dotenv import load_dotenv

from langchain.mcp import MCPAdapter
from langchain_anthropic import ChatAnthropic
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.agents.structured_output import ToolStrategy
from langfuse.langchain import CallbackHandler
from langchain_core.runnables import RunnableConfig
from langfuse import get_client, propagate_attributes

from coach.schemas import Finding


load_dotenv()


lf = get_client()



model_name = "claude-haiku-5-5"

config = {
    "mcpServers": {
        "dota-tools": {"command": sys.executable, "args": ["-m", "coach.mcp_server.server"]},
    }
}
print("-"*50)


class submit_finding(Finding): # subclass trick
    """Submit your final finding for the hypothesis. Call it once, alone, after you have verified your evidence with verify_claim."""


async def main(hypothesis: str, match_id: str):
    run_id = uuid.uuid4().hex[:8]
    with lf.start_as_current_observation(input={"hypothesis": hypothesis, "match_id": match_id}, 
                                         as_type="span", name="investigate") as root:
        with propagate_attributes(trace_name="investigate",
                                  metadata={"system": "langgraph", "match_id": str(match_id), "run_id": run_id}):
            async with MCPAdapter(config) as adapter:
                prompt = await adapter.client.get_prompt("investigator", {"hypothesis": hypothesis, "match_id": str(match_id)}) # type: ignore
                # print(prompt.messages[0])
                model = ChatAnthropic(
                    model_name=model_name,
                    max_tokens_to_sample=3000,
                    output_config={"effort": "low"},
                    timeout=60,
                    stop=None
                )
                tools = await adapter.list_tools()
                agent = create_agent(
                    model=model,
                    tools=tools,
                    system_prompt=prompt.messages[0].content.text, # type: ignore
                    response_format=ToolStrategy(submit_finding),
                    middleware=[ToolCallLimitMiddleware(run_limit=8)]
                )

                # print(agent)
                # print(agent.get_graph().draw_mermaid())

                lf_config: RunnableConfig = {"callbacks": [CallbackHandler()], "recursion_limit": 25}
                result = await agent.ainvoke({"messages": [{"role": "user", "content": "Begin the investigation."}]}, config=lf_config)
                print(result["structured_response"])
                print(f"length = {len(result["messages"])}")

                root.update(output={"finding": result["structured_response"].model_dump(),
                                    "messages": len(result["messages"])})
                print("trace:", lf.get_trace_url())
                lf.flush()

match_id = "9041884546"
hypothesis = "The Radiant lost its lead because of repeated deaths before the 15 minute mark"
asyncio.run(main(hypothesis, match_id))