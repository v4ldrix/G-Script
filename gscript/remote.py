"""Phone access: a small LAN web server (opt-in) that serves the phone app and its API."""
import hmac
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from . import access, preview
from .pairing import PairCode

WEB = Path(__file__).parent / "web"
STATIC = {
    "/app": ("app.html", "text/html; charset=utf-8"),
    "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json"),
    "/icon-192.png": ("icon-192.png", "image/png"),
    "/icon-512.png": ("icon-512.png", "image/png"),
}


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class DeviceStore:
    """Tokens of paired phones, kept on disk so pairing survives restarts."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        try:
            self.tokens = list(json.loads(self.path.read_text()))
        except (OSError, ValueError):
            self.tokens = []

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.tokens))

    def add(self):
        with self._lock:
            tok = secrets.token_urlsafe(24)
            self.tokens.append(tok)
            self._save()
            return tok

    def check(self, tok):
        return bool(tok) and any(hmac.compare_digest(tok.encode(), t.encode()) for t in list(self.tokens))

    def clear(self):
        with self._lock:
            self.tokens = []
            self._save()


class Remote:
    def __init__(self, hub, session, state_dir=None, port=8766):
        self.hub, self.session, self.port = hub, session, port
        self.dir = Path(state_dir) if state_dir is not None else Path.home() / ".gscript"
        self.devices = DeviceStore(self.dir / "devices.json")
        self.pair = PairCode(on_rotate=lambda c: print(f"[g-script] New phone code: {c}", flush=True))
        self.secret = access.new_secret()          # long secret: the only way to pair over the internet
        self.limiter = access.PairLimiter()
        self.requests = access.PairRequests()
        self.req_limiter = access.KeyedLimiter()
        self.server = None
        self.bound_port = None
        self._last_err = None

    # ----- persisted on/off choice -----
    def _cfg_path(self):
        return self.dir / "config.json"

    def _load_cfg(self):
        try:
            return json.loads(self._cfg_path().read_text())
        except (OSError, ValueError):
            return {}

    def _save_cfg(self, **kw):
        cfg = self._load_cfg()
        cfg.update(kw)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._cfg_path().write_text(json.dumps(cfg))

    def saved_enabled(self):
        return bool(self._load_cfg().get("phone"))

    def pending_pairs(self):
        return self.requests.pending()

    def decide_pair(self, rid, approve):
        ok = self.requests.decide(rid, approve, self.devices.add)
        if ok:
            self.hub.log("Phone allowed" if approve else "Phone request declined")
        return ok

    def try_pair(self, attempt):
        """The QR link's long secret, or the 6-digit code."""
        if hmac.compare_digest(access.norm_secret(attempt).encode(), self.secret.encode()):
            self.secret = access.new_secret()
            return True
        if self.pair.try_code(str(attempt).strip()):
            return True
        return False

    # ----- lifecycle -----
    @property
    def enabled(self):
        return self.server is not None

    def url(self):
        return f"http://{lan_ip()}:{self.bound_port}" if self.enabled else ""

    def enable(self):
        if self.server:
            return
        candidates = [0] if self.port == 0 else range(self.port, self.port + 10)
        for p in candidates:
            try:
                self.server = ThreadingHTTPServer(("0.0.0.0", p), make_handler(self))
                break
            except OSError:
                continue
        else:
            raise OSError("no free port for the phone server")
        self.bound_port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self._save_cfg(phone=True)

    def disable(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        self._save_cfg(phone=False)

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def reset_devices(self):
        self.devices.clear()
        self.pair.rotate()
        self.secret = access.new_secret()

    def status(self):
        lan = self.url()
        return {"enabled": self.enabled, "url": lan, "code": self.pair.code,
                "devices": len(self.devices.tokens),
                "preview_tool": preview.find_tool(self.session.tools),
                "secret": self.secret,
                "lan": {"url": lan, "link": f"{lan}/app#pair={self.secret}" if lan else ""}}

    # ----- previews -----
    def capture_async(self, delay=0.0):
        if self.enabled:
            threading.Thread(target=self._capture, args=(delay,), daemon=True).start()

    def _capture(self, delay):
        time.sleep(delay)
        res, err = preview.capture(self.session.client, self.session.tools)
        if res:
            self._last_err = None
            self.hub.event("preview", "", img=self.hub.store_image(*res))
        elif err != self._last_err:  # don't repeat the same complaint
            self._last_err = err
            self.hub.event("note", f"Preview unavailable: {err}")


def make_handler(remote):
    hub, session = remote.hub, remote.session

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", cache="no-store"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj).encode())

        def _client_ip(self):
            return self.client_address[0]      # never trust proxy headers: there is no proxy

        def _auth(self):
            if remote.devices.check(self.headers.get("X-GScript-Token", "")):
                return True
            self._json(401, {"error": "not paired"})
            return False

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 100_000:
                raise ValueError("body too large")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            path, _, qs = self.path.partition("?")
            if path == "/":
                self.send_response(302)
                self.send_header("Location", "/app")
                self.end_headers()
                return
            if path in STATIC:
                name, ctype = STATIC[path]
                try:
                    return self._send(200, (WEB / name).read_bytes(), ctype)
                except OSError:
                    return self._json(404, {"error": "missing file"})
            if path == "/pair/status":
                rid = parse_qs(qs).get("id", [""])[0]
                return self._json(200, remote.requests.status(rid))
            if not self._auth():
                return
            if path == "/state":
                try:
                    since = int(parse_qs(qs).get("since", ["0"])[0])
                except ValueError:
                    since = 0
                return self._json(200, {
                    "events": hub.since(since), "last": hub.last_id(), "ext": hub.ext_view(),
                    "pending": hub.pending,
                    "studio": {"connected": bool(session.client.alive and session.tools), "tools": len(session.tools)},
                    "preview": bool(preview.find_tool(session.tools)),
                })
            if path.startswith("/img/"):
                try:
                    img = hub.image(int(path[5:]))
                except ValueError:
                    img = None
                if not img:
                    return self._json(404, {"error": "no such image"})
                return self._send(200, img[0], img[1], cache="private, max-age=3600")
            self._json(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.partition("?")[0]
            try:
                data = self._body()
            except (ValueError, json.JSONDecodeError) as e:
                return self._json(400, {"error": str(e)})
            if path == "/pair/request":
                if not remote.req_limiter.hit(self._client_ip()):
                    return self._json(429, {"error": "Too many requests. Try again in a few minutes."})
                req = remote.requests.create(data.get("name") or self.headers.get("User-Agent", ""), self._client_ip())
                if req is None:
                    return self._json(429, {"error": "Other requests are waiting. Answer them on your PC first."})
                remote.hub.log(f"A phone wants to connect: {req['words']}")
                return self._json(200, {"id": req["id"], "words": req["words"], "ttl": int(remote.requests.ttl)})
            if path == "/pair":
                wait = remote.limiter.locked_for()
                if wait:
                    return self._json(429, {"error": f"Too many tries. Wait about {wait // 60 + 1} min."})
                if remote.try_pair(str(data.get("code", ""))):
                    remote.limiter.ok()
                    return self._json(200, {"token": remote.devices.add()})
                remote.limiter.fail()
                return self._json(403, {"error": "wrong code"})
            if not self._auth():
                return
            if path == "/send":
                text = str(data.get("text", "")).strip()
                if not text:
                    return self._json(400, {"error": "empty message"})
                return self._json(200, {"id": hub.queue_prompt(text)})
            if path == "/decision":
                ok = hub.decide(str(data.get("id", "")), bool(data.get("approve")))
                return self._json(200, {"ok": ok})
            if path == "/stop":
                hub.request_stop()
                return self._json(200, {"ok": True})
            if path == "/preview":
                if not preview.find_tool(session.tools):
                    return self._json(200, {"ok": False, "error": "Studio has no screenshot tool"})
                remote.capture_async(0)
                return self._json(200, {"ok": True})
            self._json(404, {"error": "not found"})

    return Handler
