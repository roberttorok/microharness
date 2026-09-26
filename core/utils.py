from core.paths import PROMPTS_DIR


def create_system_prompt(skills):
    template = (PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
    return template.replace("$SKILLS_PLACEHOLDER", skills)


def create_skill_switch_tool(skills):
    nl = "\n"
    skill_switch_tool = {
        "type": "function",
        "function": {
            "name": "switch_skill",
            "description": "Switch your internal skill to a specialized expert based on the user's topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "enum": list(x["name"] for x in skills),
                        "description": f"""Which skill to switch to. Available skills:

{nl.join([f"{x['name']} - {x['meta']['description']}" for x in skills])}
"""
                    }
                },
                "required": ["skill_name"]
            }
        }
    }
    return skill_switch_tool
