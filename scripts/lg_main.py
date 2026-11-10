import sys
import asyncio
import uuid
from dotenv import load_dotenv

from langfuse.langchain import CallbackHandler
from langfuse import get_client, propagate_attributes

from langchain.mcp import MCPAdapter
from langchain_anthropic import ChatAnthropic

from coach.systems.langgraph.main_graph import build_main_graph


load_dotenv()


lf = get_client()


model_name = "claude-haiku-5-5"


MCP_CONFIG = {
    "mcpServers": {
        "dota-tools": {"command": sys.executable, "args": ["-m", "coach.mcp_server.server"]},
    }
}
print("-"*50)


async def main(question: str, match_id: str):

    async def get_prompt(name: str, args: dict[str, str]) -> str:
        p = await adapter.client.get_prompt(name, args)  # type: ignore
        return p.messages[0].content.text  # type: ignore

    run_id = uuid.uuid4().hex[:8]
    with lf.start_as_current_observation(input={"question": question, "match_id": match_id}, 
                                         as_type="span", name="main") as root:
        with propagate_attributes(trace_name="main",
                                  metadata={"system": "langgraph", "match_id": str(match_id), "run_id": run_id}):
            async with MCPAdapter(MCP_CONFIG) as adapter:

                tools = await adapter.list_tools()

                model = ChatAnthropic(
                    model_name=model_name,
                    max_tokens_to_sample=3000,
                    output_config={"effort": "low"},
                    timeout=60,
                    stop=None
                )

                handler = CallbackHandler()

                graph = build_main_graph(tools=tools, model=model, get_prompt=get_prompt,
                                         max_tool_calls=8, max_attempts=2)

                try:
                    state = await graph.ainvoke(
                        {"question": question, "match_id": match_id, "plan": None, "tokens": 0, "results": []},
                        config={"callbacks": [handler]},
                    )

                    print(state["results"], state["plan"], state["tokens"])

                    root.update(output={"result": state["results"],
                                        "plan": state["plan"],
                                        "tokens": state["tokens"],
                                        })

                except Exception as e:
                    print(repr(e))

                print("trace:", lf.get_trace_url())
                lf.flush()



match_id = "9041884546"
question = "What were the key mistakes?"
asyncio.run(main(question, match_id)) 