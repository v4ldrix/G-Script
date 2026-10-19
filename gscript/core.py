"""Session: the agent loop rules. Takes model text in, returns what to do next."""
import secrets
import threading
from dataclasses import dataclass

from .mcp_client import McpError, NullClient
from .protocol import format_error, format_result, format_skipped, parse
from .rules import REMINDER, build_rules

TAIL_OK = ("All steps succeeded. If the user's request is now fully done, reply with a short plain-text "
           "summary ending with the word Done and no gscript blocks. Otherwise send ONE message with "
           "everything still needed.")
TAIL_FAIL = ("A step failed. Fix only what failed and resend only what is still needed. "
             "Do not redo steps that succeeded.")


@dataclass
class Policy:
    read_only: frozenset = frozenset()   # extra tool names treated as read-only
    approve_all: bool = False            # skip approval prompts (user opt-in)
    max_steps: int = 60                  # tool calls per session before stopping
    max_calls_per_message: int = 40
    max_result_chars: int = 8000
    reminder_every: int = 3              # short reminder every N result messages


class Session:
    def __init__(self, client=None, policy=None, project_rules=""):
        self.client = client or NullClient()
        self.policy = policy or Policy()
        self.project_rules = project_rules
        self.tools = {}
        self.steps = 0
        self.rounds = 0
        self.pending = {}
        self._lock = threading.RLock()

    def load_tools(self):
        self.tools = {t["name"]: t for t in self.client.list_tools()}
        return list(self.tools)

    def rules(self):
        return build_rules(list(self.tools.values()), self.project_rules)

    def reset(self):
        with self._lock:
            self.steps = 0
            self.rounds = 0
            self.pending.clear()

    def is_read_only(self, name):
        if name in self.policy.read_only:
            return True
        ann = (self.tools.get(name) or {}).get("annotations") or {}
        return ann.get("readOnlyHint") is True

    def _send(self, reply, count=0):
        return {"status": "send", "reply": reply, "steps": self.steps, "count": count}

    def handle_message(self, text):
        """status: waiting | finished | send | approval | limit"""
        with self._lock:
            p = parse(text)
            if p.incomplete:
                return {"status": "waiting", "reply": None, "steps": self.steps}
            if p.errors:
                return self._send(format_error(" ".join(p.errors) +
                                  ' Use: {"tool": "name", "args": {...}} inside a gscript block.', REMINDER))
            if not p.calls:
                return {"status": "finished", "reply": None, "steps": self.steps}
            calls = p.calls
            if len(calls) > self.policy.max_calls_per_message:
                return self._send(format_error(
                    f"Too many tool calls in one message ({len(calls)}; max {self.policy.max_calls_per_message}). "
                    "Combine steps, for example into one Luau script.", REMINDER))
            unknown = sorted({c.tool for c in calls if c.tool not in self.tools})
            if unknown:
                return self._send(format_error(
                    f"Unknown tool(s): {', '.join(unknown)}. Available: {', '.join(self.tools) or 'none'}. "
                    "Nothing was run.", REMINDER))
            if self.steps + len(calls) > self.policy.max_steps:
                return {"status": "limit", "reply": None, "steps": self.steps}
            if not self.policy.approve_all and any(not self.is_read_only(c.tool) for c in calls):
                aid = secrets.token_hex(4)
                self.pending[aid] = calls
                return {"status": "approval", "reply": None, "steps": self.steps,
                        "pending": {"id": aid, "tool": calls[0].tool, "args": calls[0].args,
                                    "calls": [{"tool": c.tool, "args": c.args} for c in calls]}}
            return self._execute(calls)

    def approve(self, aid, ok):
        with self._lock:
            calls = self.pending.pop(aid, None)
            if calls is None:
                return self._send(format_error("That approval request no longer exists."))
            if not ok:
                return self._send(format_error(
                    "The user declined these actions. Do not retry them; ask what they want instead."))
            return self._execute(calls)

    def _execute(self, calls):
        parts, failed, ran = [], False, 0
        for c in calls:
            if failed:
                parts.append(format_skipped(c.tool))
                continue
            self.steps += 1
            ran += 1
            try:
                is_err, text = self.client.call_tool(c.tool, c.args)
            except McpError as e:
                is_err, text = True, str(e)
            limit = self.policy.max_result_chars
            if len(text) > limit:
                text = text[:limit] + f"\n[truncated {len(text) - limit} characters; ask for a narrower query]"
            parts.append(format_result(c.tool, not is_err, text))
            failed = is_err
        self.rounds += 1
        parts.append("[g-script] " + (TAIL_FAIL if failed else TAIL_OK))
        n = self.policy.reminder_every
        if n and self.rounds % n == 0:
            parts.append(f"[g-script reminder] {REMINDER}")
        return self._send("\n\n".join(parts), ran)
