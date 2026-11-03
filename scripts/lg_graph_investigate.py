import sys
import asyncio
import uuid
import operator
from dotenv import load_dotenv
from typing import Annotated


from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler
from langfuse import get_client, propagate_attributes

from langchain.mcp import MCPAdapter
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
# from langchain.agents import create_agent
# from langchain.agents.middleware import ToolCallLimitMiddleware
# from langchain.agents.structured_output import ToolStrategy
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from coach.schemas import Finding


load_dotenv()


lf = get_client()


model_name = "claude-haiku-5-5"
MAX_TOOL_CALLS = 1


config = {
    "mcpServers": {
        "dota-tools": {"command": sys.executable, "args": ["-m", "coach.mcp_server.server"]},
    }
}
print("-"*50)


class submit_finding(Finding): # subclass trick
    """Submit your final finding for the hypothesis. Call it once, alone, after you have verified your evidence with verify_claim."""


class State(MessagesState):
    tokens: Annotated[int, operator.add]
    tool_calls: Annotated[int, operator.add]


async def main(hypothesis: str, match_id: str):

    async def call_model(state: State):
        text = prompt.messages[0].content.text # type: ignore
        system = SystemMessage(content=text)
        messages = [system] + state["messages"]
        reply = await model_with_tools.ainvoke(messages)
        usage = reply.usage_metadata or {}
        tool_calls = [c for c in reply.tool_calls if c["name"] != "submit_finding"]
        return {"messages": [reply], 
                "tokens": usage.get("input_tokens", 0)  + usage.get("output_tokens", 0),
                "tool_calls": len(tool_calls)}


    def route(state: State):
        last = state["messages"][-1]
        names = [call["name"] for call in last.tool_calls] # type: ignore
        if "submit_finding" in names:
            return END
        elif names:
            if state["tool_calls"] > MAX_TOOL_CALLS: # budget spent
                return END
            return "tools"
        else:
            return END


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
                tool_node = ToolNode(tools)

                model_with_tools = model.bind_tools(tools + [submit_finding])
                
                # agent = create_agent(
                #     model=model,
                #     tools=tools,
                #     system_prompt=prompt.messages[0].content.text, # type: ignore
                #     response_format=ToolStrategy(submit_finding),
                #     middleware=[ToolCallLimitMiddleware(run_limit=8)]
                # )

                builder = StateGraph(State)
                builder.add_node("model", call_model)
                builder.add_node("tools", tool_node)
                builder.add_edge(START, "model")
                builder.add_conditional_edges("model", route)
                builder.add_edge("tools", "model")
                graph = builder.compile()

                lf_config: RunnableConfig = {"callbacks": [CallbackHandler()], "recursion_limit": 25}
                
                initial: State = {
                    "messages": [HumanMessage(content="Begin the investigation.")],
                    "tokens": 0,
                    "tool_calls": 0,
                }
                result = await graph.ainvoke(initial, config=lf_config)

                print(f"tokens = {result["tokens"]} | tool_calls = {result["tool_calls"]}")
                print(f"length = {len(result["messages"])}")

                last = result["messages"][-1]
                print(last.tool_calls)

                names = [c["name"] for c in last.tool_calls] 

                if "submit_finding" in names:
                    reason = "submitted"
                elif result["tool_calls"] >= MAX_TOOL_CALLS:                     # 
                    reason = "budget"
                else:
                    reason = "no_tool_call"

                print("reason =", reason)


                root.update(output={"reason": reason,
                                    "tokens": result["tokens"],
                                    "tool_calls_made": result["tool_calls"],
                                    "messages": len(result["messages"])})
                print("trace:", lf.get_trace_url())
                lf.flush()

match_id = "9041884546"
hypothesis = "The Radiant lost its lead because of repeated deaths before the 15 minute mark"
asyncio.run(main(hypothesis, match_id)) 