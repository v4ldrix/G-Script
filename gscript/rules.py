"""The rules message sent to the AI when the user clicks Start g-script."""
RULES_VERSION = 1
F = "`" * 3

REMINDER = ("Finish the request in one message with several gscript blocks, build only what was asked, "
            "and when everything succeeded reply with a short summary ending in Done and no blocks.")

CORE = f"""You are connected to a live Roblox Studio session through g-script. You act in Studio by calling tools.

HOW TO CALL TOOLS
Write each call as a fenced block tagged gscript containing JSON. You can put SEVERAL blocks in one message; they run in order:

{F}gscript
{{"tool": "TOOL_NAME", "args": {{"arg": "value"}}}}
{F}

HOW TO WORK
1. Finish the whole request in ONE message. Plan briefly, then put every step in that message as gscript blocks. Prefer one tool call that does a lot (for example one Luau script that builds everything) over many small calls.
2. Only look around first if you truly need to (existing names, a script's contents). Do that in one read-only message, then build everything in the next.
3. Build exactly what the user asked for. No extra parts, no placeholder junk, no unrelated changes. Put what you create inside one clearly named Model or Folder.
4. When Luau changes the place, call ChangeHistoryService:SetWaypoint before and after so the user can undo with Ctrl+Z.
5. After a message with blocks, write nothing else and wait. The results come back as ONE message starting with [g-script result].
6. If every step succeeded, reply with a short plain-text summary ending with the word Done, and NO gscript blocks. Do not keep going or "improve" things.
7. If a step failed, fix only what failed and resend only what is still needed.
8. Use only the tools listed below with exactly the argument names shown. Never say something was done unless a result confirmed it.
9. Never delete or overwrite anything the user did not ask you to touch.
"""


def _arg(name, spec, required):
    t = spec.get("type", "any") if isinstance(spec, dict) else "any"
    if isinstance(spec, dict) and spec.get("enum"):
        t = "|".join(str(v) for v in spec["enum"])
    return f"{name}{'*' if name in required else ''}: {t}"


def _tool_line(tool):
    schema = tool.get("inputSchema") or {}
    required = set(schema.get("required", []))
    props = schema.get("properties") or {}
    args = ", ".join(_arg(n, sp, required) for n, sp in props.items())
    desc = (tool.get("description") or "").strip().splitlines()
    return f"- {tool['name']}({args}): {desc[0] if desc else 'no description'}"


def build_rules(tools, project_rules=""):
    out = [f"[g-script rules v{RULES_VERSION}]", CORE, "TOOLS (* = required argument)"]
    out += [_tool_line(t) for t in tools] or ["(none loaded)"]
    if project_rules.strip():
        out += ["", "PROJECT RULES FROM THE USER", project_rules.strip()]
    out += ["", "Reply with one short sentence confirming you understand, then wait for the user's request."]
    return "\n".join(out)
