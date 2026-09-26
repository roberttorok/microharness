import json
import re

from models.common import probe_tools

_DECODER = json.JSONDecoder()

_MARKERS = ("<|python_tag|>", "<|eom_id|>", "<|eot_id|>")


def _json_objects(text):
    """Yield (object, start, end) for every complete JSON object in text.

    There is nothing to match on, so the braces have to be found by actually
    parsing - a regex cannot balance nested objects, and tool arguments nest.
    The instruction line's `{"name": function name, ...}` is not valid JSON
    (the value is unquoted), so it drops out here for free.
    """
    index = 0
    while True:
        start = text.find("{", index)
        if start == -1:
            return
        try:
            obj, end = _DECODER.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1      # a brace that starts nothing parseable
            continue
        index = end
        if isinstance(obj, dict):
            yield obj, start, end


def _calls(message):
    """The JSON objects in message that look like tool calls, with their spans."""
    found = []
    for obj, start, end in _json_objects(message):
        name = obj.get("name")
        arguments = obj.get("parameters", obj.get("arguments", {}))
        if isinstance(name, str) and isinstance(arguments, dict):
            found.append(({"name": name, "arguments": arguments}, start, end))
    return found


def parse_llama_tool_calls(message):
    return [call for call, _, _ in _calls(message)]


def llama_remove_tool_calling(message):
    for _, start, end in reversed(_calls(message)):
        message = message[:start] + message[end:]
    for marker in _MARKERS:
        message = message.replace(marker, "")
    # a list of calls leaves its brackets and commas behind; that is not content
    if not re.search(r"[^\s\[\],]", message):
        return ""
    return message.strip()


def render_llama_tools(tokenizer, tools):
    """The declarations exactly as the chat template writes them: each tool as
    JSON indented four spaces, separated by a blank line."""
    probe = probe_tools(tokenizer, tools)
    return "\n\n".join(
        probe[start:end]
        for obj, start, end in _json_objects(probe)
        if obj.get("type") == "function"
    )
