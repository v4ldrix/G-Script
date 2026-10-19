"""Tiny fake MCP server (stdio) standing in for Roblox Studio in tests."""
import json
import sys

TOOLS = [
    {"name": "get_tree", "description": "Read the explorer tree.\nMore text.",
     "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": []},
     "annotations": {"readOnlyHint": True}},
    {"name": "run_luau", "description": "Run Luau code in Studio.",
     "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "big", "description": "Returns a huge result.", "inputSchema": {"type": "object", "properties": {}},
     "annotations": {"readOnlyHint": True}},
    {"name": "screen_capture", "description": "Capture the Studio viewport.",
     "inputSchema": {"type": "object", "properties": {"datamodel_type": {"type": "string", "enum": ["Edit", "Server"]}},
                     "required": ["datamodel_type"]},
     "annotations": {"readOnlyHint": True}},
]
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def reply(mid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": mid}
    msg.update({"error": error} if error else {"result": result})
    print(json.dumps(msg), flush=True)


for line in sys.stdin:
    m = json.loads(line)
    mid, method, p = m.get("id"), m.get("method"), m.get("params", {})
    if method == "initialize":
        reply(mid, {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "fake"}})
    elif method == "tools/list":
        reply(mid, {"tools": TOOLS})
    elif method == "tools/call":
        name, args = p["name"], p.get("arguments", {})
        if name == "get_tree":
            reply(mid, {"content": [{"type": "text", "text": "Workspace > Baseplate"}]})
        elif name == "run_luau":
            if "error" in args.get("code", ""):
                reply(mid, {"content": [{"type": "text", "text": "script error"}], "isError": True})
            else:
                reply(mid, {"content": [{"type": "text", "text": "ran: " + args.get("code", "")}]})
        elif name == "screen_capture":
            ok = args.get("datamodel_type") in ("Edit", "Server")
            reply(mid, {"content": [{"type": "image", "data": PNG, "mimeType": "image/png"}]} if ok
                  else {"content": [{"type": "text", "text": "bad datamodel_type"}], "isError": True})
        elif name == "big":
            reply(mid, {"content": [{"type": "text", "text": "x" * 50000}]})
        else:
            reply(mid, error={"code": -32602, "message": "unknown tool"})
    elif mid is not None:
        reply(mid, error={"code": -32601, "message": "no such method"})
