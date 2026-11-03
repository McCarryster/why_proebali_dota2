import sys
import asyncio
from langchain.mcp import MCPAdapter


config = {
    "mcpServers": {
        "dota-tools": {"command": sys.executable, "args": ["-m", "coach.mcp_server.server"]},
    }
}


async def main():
    async with MCPAdapter(config) as adapter:
        tools = await adapter.list_tools()
        for t in tools:
            print(t.name, t.description[:80], t.args_schema)
            print("-"*50)

asyncio.run(main())