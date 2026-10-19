import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from gscript import launch, preview
from gscript.bridge import make_server
from gscript.core import Session
from gscript.hub import Hub
from gscript.mcp_client import McpClient
from gscript.remote import Remote

FAKE = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")
F = "`" * 3
EXT = "chrome-extension://abc"


def block(obj):
    return f"{F}gscript\n{json.dumps(obj)}\n{F}"


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read()
            try:
                return r.status, json.loads(body)
            except ValueError:
                return r.status, body
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except ValueError:
            return e.code, {}


class PhoneBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = McpClient([sys.executable, FAKE], timeout=10)
        self.client.start()
        self.session = Session(self.client)
        self.session.load_tools()
        self.hub = Hub()
        self.remote = Remote(self.hub, self.session, state_dir=self.tmp.name, port=0)
        self.remote.enable()
        self.local = make_server(self.session, "secret", port=0, hub=self.hub, remote=self.remote)
        threading.Thread(target=self.local.serve_forever, daemon=True).start()
        self.rp = self.remote.bound_port
        self.lp = self.local.server_address[1]

    def tearDown(self):
        self.local.shutdown()
        self.local.server_close()
        self.remote.close()
        self.client.close()
        self.tmp.cleanup()

    def phone(self, path, data=None, token=None):
        h = {"X-GScript-Token": token} if token else {}
        return http(f"http://127.0.0.1:{self.rp}{path}", data, h)

    def ext(self, path, data=None):
        return http(f"http://127.0.0.1:{self.lp}{path}", data, {"X-GScript-Token": "secret", "Origin": EXT})

    def pair_phone(self):
        code, body = self.phone("/pair", {"code": self.remote.pair.code})
        self.assertEqual(code, 200)
        return body["token"]


class PhoneServerTests(PhoneBase):
    def test_static_app(self):
        code, body = self.phone("/app")
        self.assertEqual(code, 200)
        self.assertIn(b"g-script", body)
        self.assertEqual(self.phone("/manifest.webmanifest")[0], 200)
        self.assertEqual(self.phone("/")[0], 200)  # redirects to /app

    def test_pairing_and_auth(self):
        self.assertEqual(self.phone("/state")[0], 401)
        self.assertEqual(self.phone("/pair", {"code": "000000x"})[0], 403)
        tok = self.pair_phone()
        self.assertEqual(self.phone("/state", token="nope")[0], 401)
        self.assertEqual(self.phone("/state", token=tok)[0], 200)

    def test_pairing_survives_restart(self):
        tok = self.pair_phone()
        again = Remote(self.hub, self.session, state_dir=self.tmp.name, port=0)
        self.assertTrue(again.devices.check(tok))

    def test_lan_server_cannot_run_tools(self):
        tok = self.pair_phone()
        code, _ = self.phone("/message", {"text": block({"tool": "run_luau", "args": {"code": "x"}})}, tok)
        self.assertEqual(code, 404)

    def test_prompt_flows_to_extension(self):
        tok = self.pair_phone()
        self.assertEqual(self.phone("/send", {"text": "build a castle"}, tok)[0], 200)
        _, idle = self.ext("/ext/poll", {"active": False, "busy": False, "site": "claude.ai", "state": "Ready"})
        self.assertTrue(idle["autostart"])
        self.assertEqual(idle["prompts"], [])
        _, live = self.ext("/ext/poll", {"active": True, "busy": False})
        self.assertEqual([p["text"] for p in live["prompts"]], ["build a castle"])
        self.assertEqual(self.ext("/ext/poll", {"active": True})[1]["prompts"], [])  # delivered once
        _, st = self.phone("/state", token=tok)
        self.assertTrue(st["ext"]["connected"])
        self.assertEqual(st["events"][0]["type"], "user")

    def test_ai_reply_reaches_phone(self):
        tok = self.pair_phone()
        self.ext("/ext/event", {"type": "ai", "text": "Built it. Done."})
        _, st = self.phone("/state?since=0", token=tok)
        self.assertEqual((st["events"][-1]["type"], st["events"][-1]["text"]), ("ai", "Built it. Done."))
        _, st2 = self.phone(f"/state?since={st['last']}", token=tok)
        self.assertEqual(st2["events"], [])

    def test_approval_from_phone(self):
        tok = self.pair_phone()
        _, res = self.ext("/message", {"text": block({"tool": "run_luau", "args": {"code": "print(1)"}})})
        self.assertEqual(res["status"], "approval")
        _, st = self.phone("/state", token=tok)
        self.assertEqual(st["pending"]["id"], res["pending"]["id"])
        self.assertEqual(self.phone("/decision", {"id": "wrong", "approve": True}, tok)[1]["ok"], False)
        self.assertEqual(self.phone("/decision", {"id": res["pending"]["id"], "approve": True}, tok)[1]["ok"], True)
        _, poll = self.ext("/ext/poll", {"active": True})
        self.assertEqual(poll["decisions"], {res["pending"]["id"]: True})
        _, done = self.ext("/approve", {"id": res["pending"]["id"], "approve": True})
        self.assertIn("ran: print(1)", done["reply"])
        _, st = self.phone("/state", token=tok)
        self.assertIsNone(st["pending"])
        self.assertIn("step", [e["type"] for e in st["events"]])

    def test_stop_from_phone(self):
        tok = self.pair_phone()
        self.phone("/send", {"text": "x"}, tok)
        self.phone("/stop", {}, tok)
        _, poll = self.ext("/ext/poll", {"active": True})
        self.assertTrue(poll["stop"])
        self.assertEqual(poll["prompts"], [])
        self.assertFalse(self.ext("/ext/poll", {"active": True})[1]["stop"])

    def test_preview_roundtrip(self):
        tok = self.pair_phone()
        self.assertTrue(self.phone("/preview", {}, tok)[1]["ok"])
        img = None
        for _ in range(50):
            _, st = self.phone("/state", token=tok)
            img = next((e for e in st["events"] if e["type"] == "preview"), None)
            if img:
                break
            time.sleep(0.1)
        self.assertIsNotNone(img, "no preview event arrived")
        code, data = self.phone(f"/img/{img['img']}", token=tok)
        self.assertEqual(code, 200)
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(self.phone(f"/img/{img['img']}")[0], 401)

    def test_remote_status_and_reset(self):
        tok = self.pair_phone()
        _, st = self.ext("/remote/status")
        self.assertTrue(st["enabled"])
        self.assertEqual(st["devices"], 1)
        self.assertEqual(st["preview_tool"], "screen_capture")
        self.ext("/remote/reset", {})
        self.assertEqual(self.phone("/state", token=tok)[0], 401)


class HubTests(unittest.TestCase):
    def test_decisions_only_for_current_approval(self):
        h = Hub()
        h.set_pending({"id": "a1", "calls": [{"tool": "t", "args": {}}]})
        self.assertFalse(h.decide("other", True))
        self.assertTrue(h.decide("a1", False))
        self.assertEqual(h.poll_ext({"active": True})["decisions"], {"a1": False})
        self.assertEqual(h.poll_ext({"active": True})["decisions"], {})

    def test_event_cap_and_since(self):
        h = Hub()
        for i in range(400):
            h.event("note", str(i))
        self.assertEqual(len(h.events), 300)
        self.assertEqual(len(h.since(h.last_id() - 5)), 5)

    def test_image_cap(self):
        h = Hub()
        ids = [h.store_image(b"x", "image/png") for _ in range(20)]
        self.assertIsNone(h.image(ids[0]))
        self.assertIsNotNone(h.image(ids[-1]))


class PreviewTests(unittest.TestCase):
    def test_find_and_args(self):
        tools = {"get_tree": {}, "screen_capture": {"inputSchema": {"properties": {"d": {"enum": ["Server", "Edit"]}}, "required": ["d"]}}}
        self.assertEqual(preview.find_tool(tools), "screen_capture")
        self.assertEqual(preview.build_args(tools["screen_capture"]), ({"d": "Edit"}, []))
        self.assertIsNone(preview.find_tool({"get_tree": {}}))
        self.assertEqual(preview.build_args({"inputSchema": {"properties": {"x": {"type": "string"}}, "required": ["x"]}})[1], ["x"])


class PlatformFinderTests(unittest.TestCase):
    def test_windows(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "Roblox/Versions"
            (v / "v1").mkdir(parents=True)
            (v / "v1/StudioMCP.exe").write_text("x")
            (v / "v1/RobloxStudioBeta.exe").write_text("x")
            time.sleep(0.05)
            (v / "v2").mkdir()
            (v / "v2/StudioMCP.exe").write_text("x")  # newer leftover without Studio
            self.assertEqual(launch._find_windows({"LOCALAPPDATA": d}), v / "v1/StudioMCP.exe")
            self.assertIsNone(launch._find_windows({}))

    def test_mac(self):
        with tempfile.TemporaryDirectory() as d:
            m = Path(d) / "RobloxStudio.app/Contents/MacOS"
            m.mkdir(parents=True)
            (m / "StudioMCP").write_text("x")
            (m / "RobloxStudio").write_text("x")
            self.assertEqual(launch._find_mac([Path(d)]), m / "StudioMCP")
            self.assertIsNone(launch._find_mac([Path(d) / "nothing"]))


if __name__ == "__main__":
    unittest.main()
