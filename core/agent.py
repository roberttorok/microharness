# agent

import asyncio
import os
import signal
import sys
import time
import traceback
from transformers import AutoTokenizer
import json
from core.mcp_aggregator import register_mcp, connect_server, load_mcp_config
from core.permissions import Permissions, ALLOW, DENY
from core.images import extract_images
from contextlib import AsyncExitStack
from core.skill_reader import read_skills
from models.registry import models
import core.statusbar as statusbar
from core.paths import PROMPTS_DIR
from core.role import Role
from core.utils import create_skill_switch_tool, create_system_prompt

MAX_TOOL_ROUNDS = 40


class Agent():
    def __init__(self, stack: AsyncExitStack, model_name):
        self.stack = stack

        self.switch_model(model_name)

        self.ctx_used = 0
        self.activity = "idle"
        self.generated = 0

        self.tool_call_nr = 0
        self.skills = []
        self.mcps = []
        # model-facing name ("server__tool") -> (mcp, the server's own tool name)
        self.tool_index = {}
        self.permissions = Permissions()
        self.active_skill = ""
        self.tools = []
        self.dynamic_tools = []
        self.loaded_skill_mcps = set()
        self.raw = True
        self.awaiting = False
        self.interrupted_at = 0.0

        self.system_prompt_altering = False  # outdated
        self.messages = [
            {
                "role": Role.SYSTEM,
                "content": create_system_prompt(""),
            }
        ]

    @classmethod
    async def create(cls, stack, model_name):
        instance = cls(stack=stack, model_name=model_name)
        await instance.register_mcps()
        await instance.register_skills()
        return instance

    def find_model(self, model_name):
        selected_model = next(
            (m for m in models if m.name == model_name),
            None
        )
        if not selected_model:
            raise ValueError(f"Unknown model: {model_name}")
        return selected_model

    def switch_model(self, model_name):
        self.model = self.find_model(model_name)
        self.model.tokenizer = (
            AutoTokenizer.from_pretrained(self.model.tokenizer_id)
            if self.model.tokenizer_id else None)

        self.activity = "idle"
        pass

    async def ticking(self, label, coro):
        """Await coro while keeping the bar's elapsed counter moving.

        A tool call is one long await - without this the bar freezes for the
        five minutes an apt install takes.
        """
        task = asyncio.ensure_future(coro)
        started = time.monotonic()
        self.awaiting = True
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=0.5)
                if done:
                    self.activity = "idle"
                    self.draw_status()
                    return task.result()
                self.activity = f"{label} {time.monotonic() - started:.0f}s"
                self.draw_status()
        except asyncio.CancelledError:
            # Ctrl+C: cancelling this await does not cancel what it waits on
            task.cancel()
            raise
        finally:
            self.awaiting = False

    def catch_ctrl_c(self):
        task = asyncio.current_task()
        loop = asyncio.get_running_loop()

        def cancel_if_awaiting():
            if self.awaiting:
                task.cancel()

        def on_sigint(signum, frame):
            if time.monotonic() - self.interrupted_at < 0.5:
                return
            if self.awaiting:
                loop.call_soon_threadsafe(cancel_if_awaiting)
            else:
                raise KeyboardInterrupt

        signal.signal(signal.SIGINT, on_sigint)

    def get_tool_id(self, provided=None):
        self.tool_call_nr = self.tool_call_nr + 1
        return provided or str(self.tool_call_nr)

    async def register_skills(self):
        print("Registering skills...")
        self.skills = read_skills()
        self.tools.append(create_skill_switch_tool(self.skills))
        print("The following skills have been loaded: ")
        nl = "\n"
        print(nl.join([f"{x['name']} - {x['meta']['description']}" for x in self.skills]))

    async def register_mcps(self):
        print("Registering MCPs...")
        for name, entry in load_mcp_config().items():
            try:
                mcp = await connect_server(self.stack, name, entry)
            except Exception as e:
                while getattr(e, "exceptions", None):
                    e = e.exceptions[0]
                print(f"MCP {name} unavailable, skipping: {e!r}")
                continue
            self.mcps.append(mcp)
            self.tools.extend(self.expose_tools(mcp))

        print("\n")
        print("The following tools have been loaded: ")
        for tool in self.tools:
            if tool["type"] == "function":
                print(f"{tool['function']['name']}")
        print("\n")

    def expose_tools(self, mcp):
        declarations = []
        for tool in mcp["tools"]:
            name = f"{mcp['name']}__{tool.name}"
            self.tool_index[name] = (mcp, tool.name)
            declarations.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                    "parameters": tool.input_schema
                }
            })
        return declarations

    def resolve_tool(self, name):
        """(mcp, tool) for a model-facing name. A bare "c_compile" is accepted
        too when only one server has it: skill docs name tools that way, and
        small models copy what they read. So is a bare server name such as
        "docker-shell", when that server has exactly one tool."""
        if name in self.tool_index:
            return self.tool_index[name]
        matches = [entry for entry in self.tool_index.values()
                   if entry[1] == name]
        if len(matches) == 1:
            return matches[0]
        matches = [entry for entry in self.tool_index.values()
                   if entry[0]["name"] == name]
        return matches[0] if len(matches) == 1 else None

    def approve(self, server, tool, arguments):
        """Ask the user whether a tool call may run, unless a rule decides."""
        decision, by_rule = self.permissions.match(server, tool)
        if decision == ALLOW:
            return True
        if decision == DENY:
            print(f"\n[{server}/{tool} denied by permissions.json]")
            return False

        print(f"\n[permission] {server}/{tool}")
        print(json.dumps(arguments, indent=2, ensure_ascii=False))
        # "always" only when no rule forced the question: an explicit ask
        # rule would outrank the allow rule it writes anyway
        choices = "[y]es / [n]o" + ("" if by_rule else " / [a]lways")
        while True:
            try:
                answer = statusbar.prompt(f"Allow? {choices} ").strip().lower()
            except EOFError:
                return False        # no one to ask, e.g. piped input
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            if answer in ("a", "always") and not by_rule:
                self.permissions.always_allow(server, tool)
                return True

    def clear(self):
        print("Context cleared.")
        self.ctx_used = 0
        self.activity = "idle"
        self.generated = 0
        self.tool_call_nr = 0
        self.messages = [
            {
                "role": Role.SYSTEM,
                "content": create_system_prompt(""),
            }
        ]
        self.draw_status()

    async def ask(self, question):
        checkpoint = len(self.messages)
        ctx_used = self.ctx_used
        try:
            return await self._ask(question)
        except (KeyboardInterrupt, asyncio.CancelledError):
            del self.messages[checkpoint:]
            self.ctx_used = ctx_used
            self.interrupted_at = time.monotonic()
            self.activity = "idle"
            print("\n[interrupted - discarded]")
            self.draw_status()

    async def _ask(self, question, depth=0):
        if question:
            message = {
                "role": Role.USER,
                "content": question
            }
            text, images = extract_images(question)
            if images and self.model.vision:
                message["content"] = text
                message["images"] = images
                print(
                    f"[attached: {', '.join(os.path.basename(i['path']) for i in images)}]")
            elif images:
                print(
                    f"[{self.model.name} cannot see images - sending the text only]")
            self.messages.append(message)

        try:
            self.activity = "thinking"
            self.draw_status()

            result = self.model.provider(self)
            model_response = result["raw"]
            # the server's own count is exact; without it, keep the running
            # estimate on_token built up
            reported = result["prompt_tokens"] + result["completion_tokens"]
            if reported:
                self.ctx_used = reported
            self.activity = "idle"
            self.draw_status()

            tool_calls = result["tool_calls"]

            assistant_message = {
                "role": Role.ASSISTANT,
                "content": result["content"],
                "tool_calls": []
            }

            has_tool_call = False
            tool_responses = []
            extra_messages = []
            for tool_call in tool_calls:
                if tool_call["name"] == "switch_skill":
                    call_id = self.get_tool_id(tool_call["id"])
                    assistant_message["tool_calls"].append({
                        "id": call_id,
                        "type": "function",
                        "function": {
                                "name": tool_call["name"],
                                "arguments": tool_call["arguments"],
                        }
                    })

                    skill_name = tool_call["arguments"]["skill_name"]
                    self.active_skill = skill_name

                    skill_response = await self.ticking(
                        "switch_skill", self.switch_skill(skill_name, call_id))
                    if not skill_response:
                        # every call needs a reply - an API rejects a history
                        # with a tool call left unanswered
                        tool_responses.append({
                            "role": Role.TOOL,
                            "name": tool_call["name"],
                            "tool_call_id": call_id,
                            "content": f"There is no skill named {skill_name}."
                        })
                    else:
                        tool_responses.append({
                            "role": Role.TOOL,
                            "name": tool_call["name"],
                            "tool_call_id": call_id,
                            "content": skill_response["text"]
                        })

                        # The declarations cannot live inside the tool response:
                        # its content is wrapped in a DSL string, and the
                        # declarations carry their own string delimiters, which
                        # would close that string early. They get their own
                        # message instead, after the tool responses.
                        if skill_response["tools_text"]:
                            extra_messages.append({
                                "role": Role.USER,
                                "content": f"""The {skill_name} skill activated these additional functions. \
They are available from now on, in addition to the ones listed at the start of this conversation:

{skill_response["tools_text"]}"""
                            })

                    has_tool_call = True
                    continue

                call_id = self.get_tool_id(tool_call["id"])
                assistant_message["tool_calls"].append({
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                    }
                })

                resolved = self.resolve_tool(tool_call["name"])
                if not resolved:
                    # A made-up tool still gets a reply: dropping the call
                    # silently ended the turn, and the model never learned
                    # the tool does not exist.
                    print(f"\n[no tool named {tool_call['name']} - told the model]")
                    available = ", ".join(sorted([*self.tool_index, "switch_skill"]))
                    text = (f"Error: there is no tool named {tool_call['name']}. "
                            f"Available tools: {available}.")
                else:
                    mcp, tool_name = resolved
                    if self.approve(mcp["name"], tool_name, tool_call["arguments"]):
                        # now we process the tool calls sequantially, later maybe in parallel
                        mcp_result = await self.ticking(
                            tool_call["name"],
                            mcp["descriptor"].call_tool(
                                tool_name, arguments=tool_call["arguments"]),
                        )
                        text = "\n".join(
                            block.text for block in mcp_result.content
                            if getattr(block, "type", None) == "text"
                        )
                    else:
                        text = "The user did not permit this tool call."

                tool_responses.append({
                    "role": Role.TOOL,
                    "name": tool_call["name"],
                    "tool_call_id": call_id,
                    "content": text
                })

                has_tool_call = True

            if has_tool_call:
                self.messages.append(assistant_message)
                self.messages.extend(tool_responses)
                self.messages.extend(extra_messages)
                if depth + 1 >= MAX_TOOL_ROUNDS:
                    print(f"\n[reached {MAX_TOOL_ROUNDS} tool rounds - stopping]")
                    note = ("[Stopped: too many tool calls in a row without a "
                            "final answer.]")
                    self.messages.append({"role": Role.ASSISTANT, "content": note})
                    return note
                return await self._ask("", depth + 1)
            else:
                self.messages.append({
                    "role": Role.ASSISTANT,
                    "content": model_response
                })

            return model_response
        except Exception as e:
            print("Error: ")
            print(e)
            print("Stack:")
            traceback.print_exc()

    async def switch_skill(self, skill_name, id):
        skill = next((x for x in self.skills if x["name"] == skill_name), None)
        if not skill:
            return None

        # the new skill might have new tools, register it. only the tools added
        # by THIS switch get announced, so a later switch does not re-declare
        # everything that came before it.
        new_tools = []
        mcp_attached = skill["meta"]["mcp_server"]
        if mcp_attached and skill_name not in self.loaded_skill_mcps:
            full_path = f"skills/{skill_name}/{mcp_attached}"
            added_mcp = await register_mcp(self.stack, sys.executable, [full_path])
            # a skill's server is named after the skill: "c_dev/compile"
            added_mcp["name"] = skill_name
            self.mcps.append(added_mcp)
            self.loaded_skill_mcps.add(skill_name)

            new_tools = self.expose_tools(added_mcp)
            self.dynamic_tools.extend(new_tools)

        if self.system_prompt_altering:
            # when running locally, let's add the new skill to the system prompt so the local model put some weights on it
            self.messages[0]["content"] = create_system_prompt(skill["body"])
            return {
                "text": f"Successfully switched to the {skill_name} role. Now answer the user's question.",
                "tools_text": ""
            }

        # in order to avoid destroying K*V cache, the skill arrives as a new
        # message rather than as a rewrite of the system prompt.
        return {
            "text": f"""You are now a {skill_name} expert.

{skill["body"]}

---
Now that you know this skill, you can use it to answer the user's question.
""",
            # a raw prompt has to have the new tools spelled out in the text;
            # an API receives them in its tools list instead
            "tools_text": self.model.render_tools(self.model.tokenizer, new_tools)
            if new_tools and self.model.render_tools else ""
        }

    def on_start(self, prompt_tokens):
        self.prompt_tokens = prompt_tokens
        self.generated = 0
        self.started_at = time.monotonic()
        self.ctx_used = prompt_tokens
        self.draw_status()

    def on_token(self, token):
        print(token, end="", flush=True)
        elapsed = time.monotonic() - self.started_at
        self.generated = self.generated + 1
        self.ctx_used = self.prompt_tokens + self.generated
        self.activity = (f"generating {self.generated} tok"
                         f" @ {self.generated / elapsed:.1f}/s"
                         if elapsed > 0 else "generating")
        self.draw_status(force=False)

    def draw_status(self, force=True):
        limit = self.model.options.get("num_ctx", 4096)
        pct = 100 * self.ctx_used / limit if limit else 0
        statusbar.draw(
            f" {self.model.id} | ctx {self.ctx_used}/{limit} ({pct:.0f}%)"
            f" | {self.activity}"
            f" | skill: {self.active_skill or '-'}"
            f" | tools: {self.tool_call_nr} ",
            force=force,
        )
