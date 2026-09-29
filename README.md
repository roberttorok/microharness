# microharness

A tiny terminal agent harness.

The goal of this project is that I learn and understand:
- how agents and harnesses really work
- how tool calling works on the lowest level
- how to create and consume MCPs
- how skills work

All these have been implemented and working properly in this project.

https://github.com/user-attachments/assets/43c481ec-c879-496d-b039-ab8551406506

It talks to a model (local via ollama, or a hosted API), calls tools and can use skills.

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com) for local models (recommended — no API key needed)
- The Python packages below

## Setup

```bash
# 1. Create a virtualenv (the config expects one at .venv)
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
```

### Set up Ollama (recommended)

```bash
ollama pull qwen3.5:9b
# Ollama serves on http://localhost:11434 by default 
```

Start the agent:

```bash
python main.py
```

You start on the `qwen` model. In the prompt:

- `/model` — list available models
- `/model <name>` — switch model (e.g. `/model llama3`)
- `/clear` — clear context window
- `/exit` — quit

### Using a hosted API instead (optional)

The `chatgpt` and `openrouter` models talk to hosted APIs and need a key.
Export it, or put it in `providers/.env`:

```bash
# providers/.env
OPENAI_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...
```

## Adding a model to the registry

Models live in `models/registry.py` as `ModelSpec` entries. 

A **local Ollama** model uses the raw-prompt path, so it needs a tokenizer and
the parser functions for its chat format (Qwen, Gemma, and Llama helpers already
exist in `models/`):

```python
ModelSpec(
    name="qwen",                       # the name you type in /model
    id="qwen3.5:9b",                   # the Ollama model tag
    tokenizer_id="unsloth/Qwen3.5-9B", # HuggingFace tokenizer for templating
    tool_parser=parse_qwen_tool_calls,
    purify_content=qwen_remove_tool_calling,
    render_tools=render_qwen_tools,
    vision=True,                       # can it see images?
    options={"num_ctx": 16384},        # passed straight to Ollama
)
```

A **hosted API** model is simpler — the API does its own templating and tool
parsing, so you only set a provider and endpoint:

```python
ModelSpec(
    name="openrouter",
    id="anthropic/claude-sonnet-5",    # any tool-capable model id
    provider=openrouter_chat,
    endpoint=OPENROUTER_ENDPOINT,
    vision=True,
    options={"num_ctx": 1000000},
)
```

## Adding an MCP server

MCP servers are declared in `.mcp.json`. Each key is the server name.

A **local** server is a command the harness launches (relative paths resolve
from the project root):

```json
{
  "mcpServers": {
    "calculate": {
      "command": ".venv/bin/python",
      "args": ["./mcps/mcp_calculate.py"]
    }
  }
}
```

An **HTTP** server is one that's already running as a web service:

```json
{
  "ddg-search": {
    "type": "http",
    "url": "http://127.0.0.1:8001/mcp"
  }
}
```

Whether a tool runs automatically or asks first is controlled by
`permissions.json` (`allow` / `ask` / `deny`, by `server` or `server/tool`).
Anything not listed is asked for on each call. `mcps/mcp_calculate.py` is a
minimal example server to copy from.

## Adding a skill

A skill is a folder under `skills/` with a `SKILL.md` file. The frontmatter
gives it a name and description; the body is the expert prompt injected when the
model switches to it. A skill may optionally bring its own MCP server.

## Recommended: DuckDuckGo search for a fully functional agent

Use `ddg-search`

```bash
.venv/bin/python src/duckduckgo_mcp_server/server.py  --transport streamable-http --port 8001
```

(See [duckduckgo-mcp-server](https://github.com/nickclyde/duckduckgo-mcp-server).)
