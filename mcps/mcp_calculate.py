from mcp.server.mcpserver import MCPServer

mcp = MCPServer("calculator")

@mcp.tool()
def add_numbers(a: int, b: int) -> str:
    """
       Adds two numbers. 
    """

    return str(a + b)

if __name__ == "__main__":
    mcp.run(transport="stdio")

