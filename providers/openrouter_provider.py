from typing import TYPE_CHECKING

from providers.chatgpt_provider import load_api_key, openai_compatible_chat

if TYPE_CHECKING:
    from core.agent import Agent


def openrouter_chat(agent: "Agent"):
    """OpenRouter speaks OpenAI's Chat Completions; only the key differs.

    The key is OPENROUTER_API_KEY, from the environment or providers/.env.
    """
    return openai_compatible_chat(
        agent, load_api_key("OPENROUTER_API_KEY"), "openrouter",
        # optional attribution: names this app on OpenRouter's dashboard
        extra_headers={"X-Title": "microharness"})
