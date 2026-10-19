"""Take a screenshot of Studio through whatever screenshot tool its MCP server offers."""
import base64
import json
import os

from .mcp_client import McpError

KEYWORDS = ("screenshot", "screen_capture", "capture")


def find_tool(tools):
    forced = os.environ.get("GSCRIPT_PREVIEW_TOOL")
    if forced:
        return forced if forced in tools else None
    for name in tools:
        if any(k in name.lower() for k in KEYWORDS):
            return name
    return None


def build_args(tool):
    """Returns (args, missing_required_names)."""
    raw = os.environ.get("GSCRIPT_PREVIEW_ARGS")
    if raw:
        try:
            return json.loads(raw), []
        except ValueError:
            pass
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    args, missing = {}, []
    for n in schema.get("required", []):
        spec = props.get(n) or {}
        if spec.get("enum"):
            args[n] = "Edit" if "Edit" in spec["enum"] else spec["enum"][0]
        elif "default" in spec:
            args[n] = spec["default"]
        elif spec.get("type") == "boolean":
            args[n] = False
        else:
            missing.append(n)
    return args, missing


def capture(client, tools):
    """Returns ((bytes, mime), None) or (None, reason)."""
    name = find_tool(tools)
    if not name:
        return None, "Studio has no screenshot tool"
    args, missing = build_args(tools[name])
    if missing:
        return None, f"screenshot tool needs {', '.join(missing)} (set GSCRIPT_PREVIEW_ARGS)"
    try:
        is_err, content = client.call_tool_full(name, args)
    except McpError as e:
        return None, str(e)
    for c in content:
        if c.get("type") == "image" and c.get("data"):
            try:
                return (base64.b64decode(c["data"]), c.get("mimeType", "image/png")), None
            except ValueError:
                return None, "screenshot data was not valid"
    text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")[:160]
    return None, "screenshot tool returned no image" + (f": {text}" if text else "")
