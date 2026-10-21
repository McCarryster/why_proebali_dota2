"""Agent-side bridge to the dota-tools MCP server (the from-scratch equivalent of
langchain-mcp-adapters): lists the server's tools in Anthropic format and forwards calls.

Usage:
    async with McpTools() as tools:
        defs = tools.definitions()
        text, is_error = await tools.call("get_events", {...})
"""
import sys
from contextlib import AsyncExitStack

from mcp import Client
from mcp.client.stdio import StdioServerParameters


class McpTools:
    async def __aenter__(self):
        # The stack lets us open the Client here and close it later in __aexit__.
        self._stack = AsyncExitStack()
        params = StdioServerParameters(command=sys.executable, args=["-m", "coach.mcp_server.server"])
        self._client = await self._stack.enter_async_context(Client(params))
        self._tools = (await self._client.list_tools()).tools
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    def definitions(self) -> list[dict]:
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in self._tools]

    async def call(self, name: str, args: dict) -> tuple[str, bool]:
        result = await self._client.call_tool(name, args)
        return result.content[0].text, result.is_error # type: ignore