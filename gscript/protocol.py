"""Parse tool calls out of model text and format results going back."""
import json
import re
from dataclasses import dataclass, field

TAG = "gscript"
_OPEN = re.compile(r"```[ \t]*" + TAG + r"[ \t]*\r?\n", re.I)
_BLOCK = re.compile(r"```[ \t]*" + TAG + r"[ \t]*\r?\n(.*?)```", re.I | re.S)


@dataclass
class Call:
    tool: str
    args: dict


@dataclass
class Parsed:
    calls: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    incomplete: bool = False  # an opening fence with no closing fence yet (still streaming)


def _loads(s):
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        # forgiving fallback: smart quotes and trailing commas
        fixed = s.replace("\u201c", '"').replace("\u201d", '"')
        fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
        return json.loads(fixed)


def parse(text):
    out = Parsed()
    blocks = _BLOCK.findall(text)
    out.incomplete = len(_OPEN.findall(text)) > len(blocks)
    for i, body in enumerate(blocks, 1):
        try:
            obj = _loads(body.strip())
        except json.JSONDecodeError as e:
            out.errors.append(f"Block {i} is not valid JSON ({e.msg}, line {e.lineno}).")
            continue
        for item in (obj if isinstance(obj, list) else [obj]):
            if not isinstance(item, dict) or not isinstance(item.get("tool"), str):
                out.errors.append(f'Block {i} must contain JSON objects with a string "tool" field.')
                continue
            args = item.get("args")
            if args is None:
                args = {}
            if not isinstance(args, dict):
                out.errors.append(f'Block {i}: "args" must be a JSON object.')
                continue
            out.calls.append(Call(item["tool"], args))
    return out


def format_result(tool, ok, text, reminder=None):
    msg = f"[g-script result] tool={tool} status={'ok' if ok else 'error'}\n{text}".rstrip()
    if reminder:
        msg += f"\n\n[g-script reminder] {reminder}"
    return msg


def format_skipped(tool):
    return f"[g-script result] tool={tool} status=skipped\nNot run because an earlier step failed."


def format_error(message, reminder=None):
    msg = f"[g-script error] {message}"
    if reminder:
        msg += f"\n\n[g-script reminder] {reminder}"
    return msg
