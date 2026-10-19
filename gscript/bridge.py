"""Local HTTP bridge (127.0.0.1 only). The browser extension talks to this."""
import hmac
import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__
from .pairing import PairCode  # noqa: F401  (re-exported)

WEB = Path(__file__).parent / "web"
EXT_DIR = Path(__file__).resolve().parent.parent / "extension"

MAX_BODY = 1_000_000
DEFAULT_ORIGINS = ("chrome-extension://", "moz-extension://")


def load_token(path):
    path = Path(path)
    if path.exists():
        return path.read_text().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


def make_server(session, token, host="127.0.0.1", port=0, origins=DEFAULT_ORIGINS,
                pair=None, hub=None, remote=None, trust=None):
    allowed_hosts = {"127.0.0.1", "localhost"}

    def track(res, declined=False):
        """Mirror what happened to the phone feed."""
        if not hub:
            return
        status = res.get("status")
        if status == "approval":
            hub.set_pending(res["pending"])
        elif status == "send" and res.get("count"):
            n = res["count"]
            hub.event("step", f"Ran {n} step{'s' if n != 1 else ''} in Studio")
            if remote:
                remote.capture_async(delay=1.5)
        elif status == "send" and declined:
            hub.event("note", "Actions declined")
        elif status == "limit":
            hub.event("note", "Step limit reached")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            origin = self.headers.get("Origin")
            if origin and self._origin_ok():
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()
            self.wfile.write(body)

        def _origin_ok(self):
            o = self.headers.get("Origin")
            return o is None or any(o.startswith(p) for p in origins)

        def _host_ok(self):
            return (self.headers.get("Host") or "").rsplit(":", 1)[0] in allowed_hosts

        def _guard(self):
            # Host check blocks DNS rebinding; origin check blocks random web pages; token blocks the rest.
            if not self._host_ok() or not self._origin_ok():
                self._json(403, {"error": "forbidden"})
                return False
            if not hmac.compare_digest(self.headers.get("X-GScript-Token", "").encode(), token.encode()):
                self._json(401, {"error": "bad token"})
                return False
            if trust is not None:
                trust.touch(self.headers.get("Origin"))
            return True

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("body too large")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_OPTIONS(self):
            if not self._host_ok() or not self._origin_ok():
                return self._json(403, {"error": "forbidden"})
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-GScript-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        # ----- desktop dashboard (no token; Host-checked, never sends CORS headers to web pages) -----
        def _ui_state(self):
            return {
                "version": __version__,
                "studio": {"connected": bool(session.client.alive and session.tools), "tools": len(session.tools)},
                "ext": hub.ext_view() if hub else None,
                "pair_code": pair.code if pair else None,
                "phone": remote.status() if remote else None,
                "extension_path": str(EXT_DIR),
                "log": list(hub.logs)[-60:] if hub else [],
                "app_mode": bool(hub and hub.app_mode),
                "ext_origin": trust.pinned if trust else "",
                "pairing": remote.pending_pairs() if remote else [],
            }

        def _ui_post(self):
            port = self.server.server_address[1]
            origin = self.headers.get("Origin")
            same = origin is None or origin.rstrip("/") in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")
            if not self._host_ok() or self.headers.get("X-GScript-UI") != "1" or not same:
                return self._json(403, {"error": "forbidden"})
            try:
                data = self._body()
                p = self.path
                if hub and p == "/ui/ping":
                    hub.ui_seen = time.time()
                    return self._json(200, {"ok": True})
                if hub and p == "/ui/quit":
                    hub.log("Quit requested from the dashboard")
                    hub.quit = True
                    return self._json(200, {"ok": True})
                if remote and p == "/ui/phone":
                    remote.enable() if data.get("enable") else remote.disable()
                    return self._json(200, remote.status())
                if remote and p == "/ui/pair/decide":
                    remote.decide_pair(str(data.get("id", "")), bool(data.get("approve")))
                    return self._json(200, {"pairing": remote.pending_pairs()})
                if trust is not None and p == "/ui/ext/forget":
                    trust.forget()
                    return self._json(200, {"ok": True})
                if remote and p == "/ui/phone/reset":
                    remote.reset_devices()
                    return self._json(200, remote.status())
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            except OSError as e:
                return self._json(500, {"error": str(e)})
            self._json(404, {"error": "not found"})

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/ui", "/ui/state", "/ui/qr.js"):
                if not self._host_ok():
                    return self._json(403, {"error": "forbidden"})
                if path == "/ui/state":
                    return self._json(200, self._ui_state())
                try:
                    body = (WEB / ("qr.js" if path == "/ui/qr.js" else "dashboard.html")).read_bytes()
                except OSError:
                    return self._json(404, {"error": "missing dashboard"})
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript" if path == "/ui/qr.js" else "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if not self._guard():
                return
            if self.path == "/status":
                return self._json(200, {"ok": True, "mcp_alive": session.client.alive,
                                        "tools": list(session.tools), "steps": session.steps})
            if self.path == "/rules":
                return self._json(200, {"rules": session.rules()})
            if self.path == "/remote/pair/pending" and remote:
                return self._json(200, {"pairing": remote.pending_pairs()})
            if self.path == "/remote/status" and remote:
                return self._json(200, remote.status())
            self._json(404, {"error": "not found"})

        def _pair(self):
            o = self.headers.get("Origin")
            if (pair is None and trust is None) or not self._host_ok() or not o or not self._origin_ok():
                return self._json(403, {"error": "forbidden"})
            try:
                data = self._body()
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            code = str(data.get("code", "")).strip()
            if code:                                   # optional manual code (not needed any more)
                if pair is not None and pair.try_code(code):
                    return self._json(200, {"token": token})
                return self._json(403, {"error": "wrong code"})
            if trust is not None and trust.allow(o):   # automatic: the first extension is trusted
                return self._json(200, {"token": token})
            self._json(403, {"error": "another browser extension is already connected"})

        def do_POST(self):
            if self.path == "/pair":
                return self._pair()
            if self.path.startswith("/ui/"):
                return self._ui_post()
            if not self._guard():
                return
            try:
                data = self._body()
                path = self.path
                if path == "/message":
                    res = session.handle_message(str(data.get("text", "")))
                    track(res)
                    return self._json(200, res)
                if path == "/approve":
                    ok = bool(data.get("approve"))
                    res = session.approve(str(data.get("id", "")), ok)
                    if hub:
                        hub.clear_pending()
                    track(res, declined=not ok)
                    return self._json(200, res)
                if path == "/reset":
                    session.reset()
                    if hub:
                        hub.clear_pending()
                    return self._json(200, {"ok": True})
                if hub and path == "/ext/poll":
                    res = hub.poll_ext(data)
                    if remote:
                        res["pairing"] = remote.pending_pairs()
                    return self._json(200, res)
                if remote and path == "/remote/pair/decide":
                    remote.decide_pair(str(data.get("id", "")), bool(data.get("approve")))
                    return self._json(200, {"pairing": remote.pending_pairs()})
                if hub and path == "/ext/event":
                    hub.event(str(data.get("type", "note"))[:12], str(data.get("text", "")))
                    return self._json(200, {"ok": True})
                if remote and path == "/remote/enable":
                    remote.enable()
                    return self._json(200, remote.status())
                if remote and path == "/remote/disable":
                    remote.disable()
                    return self._json(200, remote.status())
                if remote and path == "/remote/reset":
                    remote.reset_devices()
                    return self._json(200, remote.status())
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            except OSError as e:
                return self._json(500, {"error": str(e)})
            self._json(404, {"error": "not found"})

    return ThreadingHTTPServer((host, port), Handler)
