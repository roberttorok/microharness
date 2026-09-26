import json
import os
import requests
from typing import TYPE_CHECKING

# agent.py imports this module, so importing Agent back for real would be
# circular. The annotation only needs the name for type checkers.
if TYPE_CHECKING:
    from core.agent import Agent

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def load_api_key(name="OPENAI_API_KEY"):
    """The key from the environment, else from .env next to this file.

    The key must never live in a tracked file: .env is gitignored.
    """
    key = os.environ.get(name)
    if key:
        return key
    try:
        with open(ENV_FILE) as f:
            for line in f:
                key_name, _, value = line.strip().partition("=")
                if key_name == name and value:
                    return value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    raise RuntimeError(f"{name} is not set and not in .env")


def to_openai_messages(messages):
    """Our history -> exactly the fields Chat Completions accepts.

    The history is kept in one shape for every provider, and it differs from
    OpenAI's in small ways the API is strict about: arguments are dicts here
    but must be JSON strings there, an empty tool_calls list must be left out
    rather than sent, and tool replies carry an extra "name" field.
    """
    out = []
    for m in messages:
        if m["role"] == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": m["tool_call_id"],
                "content": m["content"],
            })
            continue

        msg = {"role": m["role"], "content": m.get("content") or ""}
        if m.get("images"):
            msg["content"] = [{"type": "text", "text": msg["content"]}] + [{
                "type": "image_url",
                "image_url": {"url": f"data:{image['mime']};base64,{image['data']}"},
            } for image in m["images"]]
        calls = m.get("tool_calls")
        if calls:
            msg["tool_calls"] = [{
                "id": c["id"],
                "type": "function",
                "function": {
                    "name": c["function"]["name"],
                    "arguments": c["function"]["arguments"]
                    if isinstance(c["function"]["arguments"], str)
                    else json.dumps(c["function"]["arguments"]),
                },
            } for c in calls]
            # a turn that only calls tools has no text
            msg["content"] = msg["content"] or None
        out.append(msg)
    return out


def iter_sse(response):
    """Yield each JSON event of a Server-Sent Events stream.

    Every event is a line `data: {...}`; the stream ends with `data: [DONE]`.
    """
    for line in response.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if not line.startswith("data:"):
            continue
        data = line[len("data:"):].strip()
        if data == "[DONE]":
            return
        yield json.loads(data)


def chatgpt_chat(agent: "Agent"):
    return openai_compatible_chat(agent, load_api_key(), "openai")


def openai_compatible_chat(agent: "Agent", api_key, label, extra_headers=None):
    """One model turn over a Chat Completions API, as plain HTTP.

    OpenAI's own, or any service that copies it (OpenRouter, ...).
    Returns the same shape as ollama_chat. Here the API parses tool calls
    itself, so raw and content are the same text.
    """
    # The API only reports the prompt size once the answer is done. Last
    # turn's total is a fair floor meanwhile: the new prompt contains it.
    agent.on_start(agent.ctx_used)

    with requests.post(
        agent.model.endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            **(extra_headers or {}),
        },
        json={
            "model": agent.model.id,
            "messages": to_openai_messages(agent.messages),
            # skill tools too: unlike the raw path, the API can only call a
            # function it was handed in this list
            "tools": agent.tools + agent.dynamic_tools,
            "stream": True,
            # without this the stream carries no token counts at all
            "stream_options": {"include_usage": True},
        },
        stream=True,
        timeout=(10, 300),
    ) as response:
        # leaving the block closes the connection, which is what tells
        # the server to stop generating when Ctrl+C lands mid-stream
        if response.status_code != 200:
            raise RuntimeError(
                f"{label} returned {response.status_code}: {response.text[:500]}")

        content = ""
        # Streamed tool calls arrive in fragments keyed by index: the first one
        # brings the id and name, the rest append pieces of the arguments JSON,
        # which only parses once the stream is over.
        calls = {}
        stats = {"prompt_tokens": 0, "completion_tokens": 0}

        for event in iter_sse(response):
            # a failure after the stream started comes as an event, not a status
            if event.get("error"):
                raise RuntimeError(f"{label} error: {event['error']}")
            if event.get("usage"):
                stats["prompt_tokens"] = event["usage"].get("prompt_tokens", 0)
                stats["completion_tokens"] = event["usage"].get("completion_tokens", 0)

            for choice in event.get("choices", []):
                delta = choice.get("delta", {})

                token = delta.get("content")
                if token:
                    agent.on_token(token)
                    content += token

                for fragment in delta.get("tool_calls") or []:
                    call = calls.setdefault(
                        fragment["index"], {"id": None, "name": "", "arguments": ""})
                    if fragment.get("id"):
                        call["id"] = fragment["id"]
                    function = fragment.get("function", {})
                    call["name"] += function.get("name") or ""
                    call["arguments"] += function.get("arguments") or ""

    tool_calls = []
    for _, call in sorted(calls.items()):
        try:
            arguments = json.loads(call["arguments"] or "{}")
        except json.JSONDecodeError:
            # hand the tool nothing rather than crash the turn; the tool's
            # own error then tells the model its arguments were bad
            arguments = {}
        tool_calls.append(
            {"id": call["id"], "name": call["name"], "arguments": arguments})

    return {
        "raw": content,
        "content": content,
        "tool_calls": tool_calls,
        **stats,
    }
