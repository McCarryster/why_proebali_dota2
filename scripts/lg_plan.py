import sys
import asyncio
import uuid
from dotenv import load_dotenv

from langchain.mcp import MCPAdapter
from langchain_anthropic import ChatAnthropic

from langfuse.langchain import CallbackHandler
from langfuse import get_client, propagate_attributes

from coach.systems.langgraph.planner import make_plan


load_dotenv()


lf = get_client()


model_name = "claude-haiku-5-5"


config = {
    "mcpServers": {
        "dota-tools": {"command": sys.executable, "args": ["-m", "coach.mcp_server.server"]},
    }
}
print("-"*50)


async def main(question: str, match_id: str):
    run_id = uuid.uuid4().hex[:8]
    with lf.start_as_current_observation(input={"question": question, "match_id": match_id}, 
                                         as_type="span", name="plan") as root:
        with propagate_attributes(trace_name="plan",
                                  metadata={"system": "langgraph", "match_id": str(match_id), "run_id": run_id}):
            async with MCPAdapter(config) as adapter:
                prompt = await adapter.client.get_prompt("planner", {"question": question, "match_id": str(match_id), "avoid": ""}) # type: ignore
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

                result = await make_plan(
                    match_id=match_id, tools=tools, model=model,
                    prompt_text=prompt_text, config={"callbacks": [handler]})

                print(f"plan = {result.plan} | tokens = {result.tokens}")

                root.update(output={"plan": result.plan.model_dump(),
                                    "tokens": result.tokens,
                                    })
                print("trace:", lf.get_trace_url())
                lf.flush()


match_id = "9041884546"
question = "What were the key mistakes?"
asyncio.run(main(question, match_id)) 