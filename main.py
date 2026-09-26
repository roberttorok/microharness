import asyncio
from transformers import AutoTokenizer
from contextlib import AsyncExitStack
from core.mcp_aggregator import mcp_init
from core.agent import Agent
import core.statusbar as statusbar
from models.registry import models

async def loop(stack):
    print("microharness 1.0")

    statusbar.setup()

    agent = await Agent.create(stack, "qwen")
    agent.catch_ctrl_c()
    agent.draw_status()

    while True:
        agent.draw_status()
        try:
            user_input = statusbar.prompt("> ")
        except EOFError:
            return

        if user_input == "/exit" or user_input == "/quit":
            return

        if user_input.startswith("/model"):
            arr = user_input.split(" ")
            if len(arr) == 1:
                nl = "\n"
                print(f"The following models are avialble:\n{nl.join(x.name for x in models)}")
            else:
                try:
                    agent.switch_model(arr[1])
                except ValueError as e:
                    print(e)

            continue

        if user_input == "/clear":
            # clears the context window
            agent.clear()
            print("Context window cleared.")
            continue

        await agent.ask(user_input)

async def start():
    async with AsyncExitStack() as stack:
        try:
            await loop(stack)
        finally:
            statusbar.teardown()

if __name__ == "__main__":
    asyncio.run(start())
