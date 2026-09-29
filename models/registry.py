from models.gemma import gemma_remove_tool_calling, parse_gemma_tool_calls, render_gemma_tools
from models.llama import llama_remove_tool_calling, parse_llama_tool_calls, render_llama_tools
from models.qwen import parse_qwen_tool_calls, qwen_remove_tool_calling, render_qwen_tools

from dataclasses import dataclass, field
from typing import Any, Callable

from providers.ollama_provider import ollama_chat
from providers.chatgpt_provider import chatgpt_chat
from providers.openrouter_provider import openrouter_chat


OLLAMA_ENDPOINT = "http://localhost:11434/api/generate"
OPENAI_ENDPOINT = "https://api.openai.com/v1/chat/completions"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


@dataclass
class ModelSpec:
    name: str
    id: str
    provider: Callable = ollama_chat
    endpoint: str = OLLAMA_ENDPOINT
    # only the raw-prompt path needs these: an API that takes messages and
    # returns structured tool calls does its own templating and parsing
    tokenizer_id: str | None = None
    tool_parser: Any = None
    purify_content: Any = None
    render_tools: Any = None
    # can the model see images at all
    vision: bool = False
    # raw path: what the chat template writes where an image goes. Ollama
    # wants "[img-N]" there instead and puts the model's own tokens back.
    image_placeholder: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


models = [
    ModelSpec(
        name="qwen",
        id="qwen3.5:9b",
        tokenizer_id="unsloth/Qwen3.5-9B",
        tool_parser=parse_qwen_tool_calls,
        purify_content=qwen_remove_tool_calling,
        render_tools=render_qwen_tools,
        vision=True,
        image_placeholder="<|vision_start|><|image_pad|><|vision_end|>",
        options={
            "temperature": 1.0,
            "top_p": 0.95,
            "top_k": 20,
            "min_p": 0.0,
            "presence_penalty": 1.5,
            "repeat_penalty": 1.0,
            "num_ctx": 16384
        }
    ),
    ModelSpec(
        name="gemma4",
        id="gemma4:12b",
        tokenizer_id="unsloth/gemma-4-12b-it",
        tool_parser=parse_gemma_tool_calls,
        purify_content=gemma_remove_tool_calling,
        render_tools=render_gemma_tools,
        vision=True,
        image_placeholder="<|image|>",
        options={"num_ctx": 16384, "stop": ["<end_of_turn>", "<tool_call|>"]}
    ),
    ModelSpec(
        name="llama3",
        id="llama3.1:8b",
        tokenizer_id="unsloth/Meta-Llama-3.1-8B-Instruct",
        tool_parser=parse_llama_tool_calls,
        purify_content=llama_remove_tool_calling,
        render_tools=render_llama_tools,
        options={
            # Meta's recommended sampling for Llama 3.1 instruct
            "temperature": 0.6,
            "top_p": 0.9,
            "num_ctx": 16384,
            # raw mode bypasses the template, so the turn separators have to
            # be named explicitly or the model writes the next turn itself
            "stop": ["<|eot_id|>", "<|eom_id|>", "<|start_header_id|>"],
        }
    ),
    ModelSpec(
        name="chatgpt",
        id="gpt-5.4-mini",
        provider=chatgpt_chat,
        endpoint=OPENAI_ENDPOINT,
        vision=True,
        options={"num_ctx": 400000},
    ),
    ModelSpec(
        name="openrouter",
        # any id from openrouter.ai/models that supports tools works here
        id="anthropic/claude-sonnet-5",
        provider=openrouter_chat,
        endpoint=OPENROUTER_ENDPOINT,
        vision=True,
        options={"num_ctx": 1000000},
    ),
]
