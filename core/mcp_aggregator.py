import asyncio
import json
import os
import re
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from core.paths import ROOT, MCP_CONFIG
from mcp.client.session import ClientSession
from contextlib import AsyncExitStack

async def register_mcp(stack: AsyncExitStack, command, args, env=None, cwd=None):
    server_params = StdioServerParameters(
        command=command, args=args, env={**os.environ, **(env or {})}, cwd=cwd)
    stdio = stdio_client(server_params)
    read_stream, write_stream = await stack.enter_async_context(stdio)
    return await open_session(stack, read_stream, write_stream)

# Connect to an MCP server that is already running as a web service.
async def register_mcp_http(stack: AsyncExitStack, url, headers=None):
    http_client = create_mcp_http_client(headers=headers)
    await stack.enter_async_context(http_client)
    read_stream, write_stream = await stack.enter_async_context(
        streamable_http_client(url, http_client=http_client))
    return await open_session(stack, read_stream, write_stream)


# ${VAR} and ${VAR:-default}, the same expansion Claude Code does in .mcp.json
ENV_VAR = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")

def expand(value):
    if isinstance(value, str):
        return ENV_VAR.sub(lambda m: os.environ.get(m.group(1), m.group(2) or ""), value)
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    return value

def load_mcp_config(path=MCP_CONFIG):
    if not path.exists():
        return {}
    with open(path) as f:
        return expand(json.load(f).get("mcpServers", {}))

async def connect_server(stack: AsyncExitStack, name, entry):
    server_stack = AsyncExitStack()
    try:
        if entry.get("type") == "http" or "url" in entry:
            mcp = await register_mcp_http(server_stack, entry["url"], entry.get("headers"))
        else:
            command = entry["command"]
            if "/" in command and not os.path.isabs(command):
                command = str(ROOT / command)
            mcp = await register_mcp(server_stack, command, entry.get("args", []),
                                     entry.get("env"), cwd=ROOT)
    except BaseException:
        await server_stack.aclose()
        raise
    stack.push_async_callback(server_stack.aclose)
    mcp["name"] = name
    return mcp

async def open_session(stack: AsyncExitStack, read_stream, write_stream):
    session_context = ClientSession(read_stream, write_stream)
    session = await stack.enter_async_context(session_context)

    await session.initialize()
    print("Connected and inited.")

    tools = []
    list_tools_resp = await session.list_tools()
    for tool in list_tools_resp.tools:
        tools.append(tool)

    return {
        "descriptor": session,
        "tools": tools
    }

async def mcp_init(stack: AsyncExitStack):
    sessions = []
    mcps = [
        StdioServerParameters(
            command="python",
            args=["read-file-mcp.py"]
        )
    ]

    print("Starting each MCP ...")
    for instance in mcps:
        stdio = stdio_client(instance)
        read_stream, write_stream = await stack.enter_async_context(stdio)
        session_context = ClientSession(read_stream, write_stream)
        session = await stack.enter_async_context(session_context)

        await session.initialize()
        print("Connected and inited.")

        tool_arr = []
        tools_resp = await session.list_tools()
        for tool in tools_resp.tools:
            tool_arr.append(tool)

        sessions.append({
            "descriptor": session,
            "tools": tool_arr
        })
    return sessions


async def loop():
    pass

async def start():
    async with AsyncExitStack() as stack:
        await mcp_init(stack)
        await loop()

if __name__ == "__main__":
    asyncio.run(start())