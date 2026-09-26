import re
from models.common import probe_tools
import json

def parse_qwen_tool_calls(message):
    tool_calls = []
    block_pattern = re.compile(r'<tool_call>(.*?)</tool_call>', re.DOTALL)
    for block in block_pattern.findall(message):
        fun_match = re.search(r'<function=([^>]+)>', block)
        if not fun_match:
            continue

        fun_name = fun_match.group(1).strip()
        parameters = {}
        param_pattern = re.compile(
            r'<parameter=([^>]+)>(.*?)</parameter>', re.DOTALL)
        for param_match in param_pattern.finditer(block):
            param_name = param_match.group(1).strip()
            param_value = param_match.group(2).strip()
            parameters[param_name] = param_value

        tool_calls.append({
            "name": fun_name,
            "arguments": parameters
        })
    return tool_calls

def qwen_remove_tool_calling(message):
    return re.sub(r'<tool_call>.*?</tool_call>', '', message, flags=re.DOTALL).strip()


def render_qwen_tools(tokenizer, tools):
    match = re.search(r'<tools>.*?</tools>', probe_tools(tokenizer, tools), re.DOTALL)
    return match.group(0) if match else ""

