from mcp.server import MCPServer, tool
from mcp import Tool

from coach.dota.digest import digest
from coach.dota.opendota import get_match


mcp = MCPServer("dota-tools")


@mcp.tool()
def fetch_match(match_id: int) -> str:
    """<2-3 sentences: when to use this, what it returns>"""
    match = get_match(match_id)
    if not match.get("version"):
        return "Match not parsed yet: ..."      # a helpful message, not a crash
    return digest(match)




if __name__ == "__main__":
    mcp.run(transport="stdio")