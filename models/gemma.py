import re
from models.common import probe_tools
import json

def parse_gemma_tool_calls(message):
    tool_calls = []
    block_pattern = re.compile(
        r'<\|tool_call>\s*call:\s*([^{\s]+)\s*\{(.*?)\}\s*(?:<tool_call\|>|$)',
        re.DOTALL)
    bare_key_pattern = re.compile(
        r'(?<=[{,\[])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:')

    for fun_name, body in block_pattern.findall(message):
        chunks = ('{' + body + '}').split('<|"|>')
        for i, chunk in enumerate(chunks):
            chunks[i] = bare_key_pattern.sub(
                r'"\1":', chunk) if i % 2 == 0 else json.dumps(chunk)

        try:
            parameters = json.loads(''.join(chunks))
        except json.JSONDecodeError:
            print(f"Could not parse arguments for {fun_name}: {body}")
            continue

        tool_calls.append({
            "name": fun_name.strip(),
            "arguments": parameters
        })
    return tool_calls


def render_gemma_tools(self, tools):
    probe = self.tokenizer.apply_chat_template(
        [{"role": "user", "content": ""}], tools=tools,
        tokenize=False, add_generation_prompt=False)
    return "".join(re.findall(r'<\|tool>.*?<tool\|>', probe, re.DOTALL))

def gemma_remove_tool_calling(message):
    # Closing tag optional: it may have been stripped as a stop sequence.
    return re.sub(r'<\|tool_call>.*?(?:<tool_call\|>|$)', '', message,
                  flags=re.DOTALL).strip()


def render_gemma_tools(tokenizer, tools):
    return "".join(re.findall(r'<\|tool>.*?<tool\|>',
                              probe_tools(tokenizer, tools), re.DOTALL))
