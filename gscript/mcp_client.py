"""Minimal MCP client over stdio (newline-delimited JSON-RPC). No dependencies."""
import collections
import itertools
import json
import subprocess
import sys
import threading


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, command, env=None, cwd=None, timeout=60.0):
        self.command = command
        self.env = env
        self.cwd = cwd
        self.timeout = timeout
        self.server_info = {}
        self.stderr_tail = collections.deque(maxlen=20)
        self._proc = None
        self._ids = itertools.count(1)
        self._pending = {}
        self._plock = threading.Lock()
        self._wlock = threading.Lock()

    # lifecycle
    def start(self):
        try:
            extra = {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # CREATE_NO_WINDOW
            self._proc = subprocess.Popen(
                self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, env=self.env, cwd=self.cwd,
                text=True, encoding="utf-8", bufsize=1, **extra,
            )
        except OSError as e:
            raise McpError(f"Could not start MCP server {self.command!r}: {e}")
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        res = self.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "g-script", "version": "0.1.0"},
        })
        self.server_info = res.get("serverInfo", {})
        self.notify("notifications/initialized")

    def close(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._proc:
            for f in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
                try:
                    f.close()
                except (OSError, ValueError):
                    pass

    @property
    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    # transport
    def _send(self, obj):
        line = json.dumps(obj) + "\n"
        with self._wlock:
            try:
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
            except (OSError, ValueError, AttributeError):
                raise McpError("MCP server is not running")

    def _read_stderr(self):
        for line in self._proc.stderr:
            self.stderr_tail.append(line.rstrip())

    def _read_stdout(self):
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            mid = msg.get("id")
            if "method" in msg:  # server-initiated request or notification
                if mid is not None:
                    if msg["method"] == "ping":
                        self._try_send({"jsonrpc": "2.0", "id": mid, "result": {}})
                    else:
                        self._try_send({"jsonrpc": "2.0", "id": mid,
                                        "error": {"code": -32601, "message": "Method not supported"}})
                continue
            with self._plock:
                slot = self._pending.pop(mid, None)
            if slot:
                slot["msg"] = msg
                slot["event"].set()
        tail = " | ".join(list(self.stderr_tail)[-3:])
        self._fail_all("MCP server exited" + (f" ({tail})" if tail else ""))

    def _try_send(self, obj):
        try:
            self._send(obj)
        except McpError:
            pass

    def _fail_all(self, reason):
        with self._plock:
            slots, self._pending = list(self._pending.values()), {}
        for slot in slots:
            slot["msg"] = {"error": {"message": reason}}
            slot["event"].set()

    # requests
    def notify(self, method, params=None):
        self._send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def request(self, method, params=None, timeout=None):
        mid = next(self._ids)
        slot = {"event": threading.Event(), "msg": None}
        with self._plock:
            self._pending[mid] = slot
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        if not slot["event"].wait(timeout or self.timeout):
            with self._plock:
                self._pending.pop(mid, None)
            raise McpError(f"Timed out waiting for {method}")
        msg = slot["msg"]
        if "error" in msg:
            raise McpError(f"{method} failed: {msg['error'].get('message', 'unknown error')}")
        return msg.get("result", {})

    def list_tools(self):
        tools, cursor = [], None
        while True:
            res = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += res.get("tools", [])
            cursor = res.get("nextCursor")
            if not cursor:
                return tools

    def call_tool_full(self, name, args, timeout=120.0):
        """Returns (is_error, content_list) with images kept."""
        res = self.request("tools/call", {"name": name, "arguments": args}, timeout=timeout)
        return bool(res.get("isError")), res.get("content", [])

    def call_tool(self, name, args, timeout=120.0):
        """Returns (is_error, text). Non-text content is replaced by a short marker."""
        is_err, content = self.call_tool_full(name, args, timeout)
        parts = []
        for c in content:
            if c.get("type") == "text":
                parts.append(c.get("text", ""))
            else:
                parts.append(f"[{c.get('type', 'content')} omitted]")
        return is_err, "\n".join(parts)


class NullClient:
    """Placeholder while Studio is not connected."""
    alive = False
    stderr_tail = ()

    def list_tools(self):
        return []

    def call_tool(self, *a, **k):
        raise McpError("Studio is not connected. Open Roblox Studio with a place loaded and MCP enabled.")

    call_tool_full = call_tool

    def close(self):
        pass
