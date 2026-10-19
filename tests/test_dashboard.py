import http.client
import json
import os
import sys
import tempfile
import threading
import unittest

from gscript.bridge import make_server
from gscript.core import Session
from gscript.hub import Hub
from gscript.mcp_client import McpClient
from gscript.pairing import PairCode
from gscript.remote import Remote

FAKE = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = McpClient([sys.executable, FAKE], timeout=10)
        self.client.start()
        self.session = Session(self.client)
        self.session.load_tools()
        self.hub = Hub()
        self.remote = Remote(self.hub, self.session, state_dir=self.tmp.name, port=0)
        self.server = make_server(self.session, "secret", port=0, hub=self.hub, remote=self.remote, pair=PairCode())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.remote.close()
        self.client.close()
        self.tmp.cleanup()

    def req(self, method, path, headers=None, body=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = dict(headers or {})
        if host:
            h["Host"] = host
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        return r.status, data

    UI = {"X-GScript-UI": "1", "Content-Type": "application/json"}

    def test_page_and_state_need_no_token(self):
        code, body = self.req("GET", "/ui")
        self.assertEqual(code, 200)
        self.assertIn(b"Quit g-script", body)
        self.assertEqual(self.req("GET", "/")[0], 200)
        code, body = self.req("GET", "/ui/state")
        st = json.loads(body)
        self.assertTrue(st["studio"]["connected"])
        self.assertEqual(len(st["pair_code"]), 6)
        self.assertTrue(st["extension_path"].endswith("extension"))

    def test_other_hosts_are_refused(self):
        for path in ("/ui", "/ui/state"):
            self.assertEqual(self.req("GET", path, host="evil.example:8765")[0], 403)

    def test_token_endpoints_still_need_the_token(self):
        self.assertEqual(self.req("GET", "/status")[0], 401)
        self.assertEqual(self.req("POST", "/message", {"X-GScript-Token": "wrong"}, {"text": "x"})[0], 401)

    def test_ui_posts_are_protected_against_other_sites(self):
        self.assertEqual(self.req("POST", "/ui/quit", {}, {})[0], 403)                      # missing header
        self.assertEqual(self.req("POST", "/ui/quit", {**self.UI, "Origin": "https://evil.example"}, {})[0], 403)
        self.assertFalse(self.hub.quit)
        self.assertEqual(self.req("POST", "/ui/quit", {**self.UI, "Origin": f"http://127.0.0.1:{self.port}"}, {})[0], 200)
        self.assertTrue(self.hub.quit)

    def test_ping_and_phone_toggle(self):
        self.assertEqual(self.hub.ui_seen, 0.0)
        self.req("POST", "/ui/ping", self.UI, {})
        self.assertGreater(self.hub.ui_seen, 0)
        code, body = self.req("POST", "/ui/phone", self.UI, {"enable": False})
        self.assertFalse(json.loads(body)["enabled"])
        code, body = self.req("POST", "/ui/phone", self.UI, {"enable": True})
        self.assertTrue(json.loads(body)["enabled"])

    def test_log_lines_reach_the_dashboard(self):
        self.hub.log("hello from the bridge")
        st = json.loads(self.req("GET", "/ui/state")[1])
        self.assertIn("hello from the bridge", st["log"][-1])


class UnicodeSafetyTests(unittest.TestCase):
    def test_pair_code_with_non_ascii_does_not_crash(self):
        pc = PairCode()
        self.assertFalse(pc.try_code("１２３４５６"))   # full-width digits
        self.assertFalse(pc.try_code("é" * 6))
        self.assertTrue(pc.try_code(pc.code))

    def test_non_ascii_token_header_is_just_unauthorized(self):
        client = McpClient([sys.executable, FAKE], timeout=10)
        client.start()
        session = Session(client)
        server = make_server(session, "secret", port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            c.request("GET", "/status", headers={"X-GScript-Token": "tøken".encode("latin-1").decode("latin-1")})
            self.assertEqual(c.getresponse().status, 401)
            c.close()
        finally:
            server.shutdown()
            server.server_close()
            client.close()


if __name__ == "__main__":
    unittest.main()
