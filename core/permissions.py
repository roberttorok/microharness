"""Which MCP tool calls may run without asking.

permissions.json:
    {"permissions": {"allow": [...], "ask": [...], "deny": [...]}}

A rule is either "server" (every tool on it) or "server/tool" (one tool).
deny beats ask beats allow, so a narrow exception always overrides a broad
rule. A call no rule matches has to be approved by the user.
"""
import json

from core.paths import PERMISSIONS

ALLOW = "allow"
ASK = "ask"
DENY = "deny"


class Permissions:
    def __init__(self, path=PERMISSIONS):
        self.path = path
        self.rules = {ALLOW: [], ASK: [], DENY: []}
        if path.exists():
            with open(path) as f:
                self.rules.update(json.load(f).get("permissions", {}))

    def match(self, server, tool):
        """The decision for a call, and whether a rule made it (False means
        nothing matched and it is the ask-by-default case)."""
        for decision in (DENY, ASK, ALLOW):
            rules = self.rules.get(decision, [])
            if server in rules or f"{server}/{tool}" in rules:
                return decision, True
        return ASK, False

    def always_allow(self, server, tool):
        self.rules[ALLOW].append(f"{server}/{tool}")
        with open(self.path, "w") as f:
            json.dump({"permissions": self.rules}, f, indent=2)
            f.write("\n")
