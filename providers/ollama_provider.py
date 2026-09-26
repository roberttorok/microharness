import requests
import json
from typing import TYPE_CHECKING

# agent.py imports this module, so importing Agent back for real would be
# circular. The annotation only needs the name for type checkers.
if TYPE_CHECKING:
    from core.agent import Agent

def with_image_parts(message):
    """A message with images, the way chat templates want it: content as a
    list of parts, one {"type": "image"} per image before the text."""
    if not message.get("images"):
        return message
    return {
        **message,
        "content": [{"type": "image"} for _ in message["images"]]
        + [{"type": "text", "text": message["content"]}],
    }


def without_image_data(message):
    """For the log: the paths, not megabytes of base64."""
    if not message.get("images"):
        return message
    return {**message, "images": [image["path"] for image in message["images"]]}


def ollama_chat(agent: "Agent"):
    """One model turn over Ollama's raw /api/generate.

    Returns the shape every provider returns:
      raw         - the text exactly as generated
      content     - the text with tool-call markup removed
      tool_calls  - [{"id": None, "name": ..., "arguments": {...}}]
      prompt_tokens, completion_tokens - 0 when the server did not say
    """
    model_response = ""

    raw_prompt = agent.model.tokenizer.apply_chat_template(
        [with_image_parts(m) for m in agent.messages],
        tokenize=False,
        tools=agent.tools,
        add_generation_prompt=True
    )

    # the template marks each image in its own way; Ollama only understands
    # "[img-N]", N indexing the images list below, in prompt order
    images = [image["data"] for m in agent.messages for image in m.get("images", [])]
    for i in range(len(images)):
        raw_prompt = raw_prompt.replace(
            agent.model.image_placeholder, f"[img-{i}]", 1)

    with open("logs/model_raw.txt", "w") as f:
        print(raw_prompt, file=f)

    with open("logs/model_messages.txt", "w") as f:
        json.dump([without_image_data(m) for m in agent.messages], f,
                  indent=2, ensure_ascii=False, default=str)

    agent.on_start(len(agent.model.tokenizer.encode(
        raw_prompt, add_special_tokens=False)))

    with requests.post(
        agent.model.endpoint,
        headers={
            "Content-Type": "application/json"
        },
        json={
            "model": agent.model.id,
            "prompt": raw_prompt,
            "raw": True,
            "images": images,
            "stream": True,
            "options": agent.model.options
        },
        stream=True
    ) as response:
        # leaving the block closes the connection, which is what tells
        # the server to stop generating when Ctrl+C lands mid-stream
        stats = {
            "prompt_tokens": 0,
            "completion_tokens": 0
        }

        if response.status_code == 200:
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line.decode('utf-8'))
                    token = chunk.get("response", "")
                    if token:
                        agent.on_token(token)
                        model_response += token

                    if chunk.get("done"):
                        stats["prompt_tokens"] = chunk.get("prompt_eval_count", 0)
                        stats["completion_tokens"] = chunk.get("eval_count", 0)
                        break
        else:
            raise RuntimeError(
                f"ollama returned {response.status_code}: {response.text[:500]}")

    # the model writes tool calls as text; they have no id of their own
    tool_calls = [
        {"id": None, **call} for call in agent.model.tool_parser(model_response)
    ]

    return {
        "raw": model_response,
        "content": agent.model.purify_content(model_response),
        "tool_calls": tool_calls,
        **stats,
    }

