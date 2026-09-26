from pathlib import Path
from core.paths import SKILLS_DIR
import yaml

def read_skills():
    skills = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8")
        skill_file = skill_md.parent.resolve()
        meta = {}
        if text.startswith("---"):
            _, frontmatter, body = text.split("---", 2)
            meta = yaml.safe_load(frontmatter)
        else:
            meta, body = {}, text

        skills.append({
            "name": meta["name"],
            "meta": meta,
            "skill_file": skill_file,
            "body": body
        })

    return skills

if __name__ == "__main__":
    read_skills()