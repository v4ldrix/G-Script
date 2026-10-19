import json
import re
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from gscript.access import KeyedLimiter, PairRequests
from gscript.bridge import make_server
from gscript.core import Session
from gscript.mcp_client import McpClient
from gscript.pairing import ExtTrust
from tests.test_phone import FAKE, PhoneBase, http

EXT_A, EXT_B = "chrome-extension://aaaaaaaa", "chrome-extension://bbbbbbbb"
UI = {"X-GScript-UI": "1", "Content-Type": "application/json"}


class ExtTrustTests(unittest.TestCase):
    def test_first_extension_is_trusted_and_others_wait(self):
        with tempfile.TemporaryDirectory() as d:
            t = ExtTrust(Path(d) / "ext", idle=60)
            self.assertTrue(t.allow(EXT_A))
            self.assertTrue(t.allow(EXT_A))
            self.assertFalse(t.allow(EXT_B))
            self.assertFalse(t.allow("https://evil.example"))
            self.assertFalse(t.allow(""))

    def test_takeover_only_after_the_first_goes_quiet(self):
        with tempfile.TemporaryDirectory() as d:
            t = ExtTrust(Path(d) / "ext", idle=0.3)
            t.allow(EXT_A)
            t.touch(EXT_A)
            self.assertFalse(t.allow(EXT_B))
            time.sleep(0.4)
            self.assertTrue(t.allow(EXT_B))          # e.g. the extension was reinstalled from another folder
            self.assertFalse(t.allow(EXT_A))

    def test_remembered_across_restarts_with_a_grace_period(self):
        with tempfile.TemporaryDirectory() as d:
            ExtTrust(Path(d) / "ext").allow(EXT_A)
            again = ExtTrust(Path(d) / "ext", idle=60)
            self.assertEqual(again.pinned, EXT_A)
            self.assertFalse(again.allow(EXT_B))

    def test_forget(self):
        with tempfile.TemporaryDirectory() as d:
            t = ExtTrust(Path(d) / "ext")
            t.allow(EXT_A)
            t.forget()
            self.assertTrue(t.allow(EXT_B))


class ExtensionPairingEndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = McpClient([sys.executable, FAKE], timeout=10)
        self.client.start()
        self.server = make_server(Session(self.client), "secret", port=0, trust=ExtTrust(Path(self.tmp.name) / "e"))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/pair"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.client.close()
        self.tmp.cleanup()

    def test_no_code_needed(self):
        code, body = http(self.url, {}, {"Origin": EXT_A})
        self.assertEqual((code, body["token"]), (200, "secret"))
        self.assertEqual(http(self.url, {}, {"Origin": EXT_A})[0], 200)

    def test_other_extensions_web_pages_and_scripts_are_refused(self):
        http(self.url, {}, {"Origin": EXT_A})
        self.assertEqual(http(self.url, {}, {"Origin": EXT_B})[0], 403)
        self.assertEqual(http(self.url, {}, {"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(http(self.url, {})[0], 403)                              # no Origin at all

    def test_a_wrong_manual_code_is_not_a_back_door(self):
        self.assertEqual(http(self.url, {"code": "123456"}, {"Origin": EXT_A})[0], 403)


class PhoneApprovalTests(PhoneBase):
    def request(self, name="Pixel 8", headers=None):
        return http(f"http://127.0.0.1:{self.rp}/pair/request", {"name": name}, headers or {})

    def status(self, rid):
        return http(f"http://127.0.0.1:{self.rp}/pair/status?id={rid}")[1]

    def decide(self, rid, ok):
        return self.ext("/remote/pair/decide", {"id": rid, "approve": ok})

    def test_approve_flow_hands_over_one_working_token(self):
        code, req = self.request()
        self.assertEqual(code, 200)
        self.assertRegex(req["words"], r"^[A-Z]+ [A-Z]+$")
        self.assertEqual(self.status(req["id"]), {"status": "pending"})
        pend = self.ext("/remote/pair/pending")[1]["pairing"]
        self.assertEqual([(p["id"], p["words"]) for p in pend], [(req["id"], req["words"])])
        self.decide(req["id"], True)
        done = self.status(req["id"])
        self.assertEqual(done["status"], "approved")
        self.assertEqual(self.phone("/state", token=done["token"])[0], 200)
        self.assertNotIn("token", self.status(req["id"]))                         # handed over exactly once
        self.assertEqual(self.ext("/remote/pair/pending")[1]["pairing"], [])

    def test_deny_gives_no_token(self):
        _, req = self.request()
        self.decide(req["id"], False)
        self.assertEqual(self.status(req["id"]), {"status": "denied"})

    def test_requests_expire(self):
        self.remote.requests.ttl = 0.2
        _, req = self.request()
        time.sleep(0.35)
        self.assertEqual(self.status(req["id"])["status"], "expired")
        self.assertEqual(self.decide(req["id"], True)[0], 200)                    # too late: nothing is granted
        self.assertEqual(self.status(req["id"])["status"], "expired")
        self.assertEqual(self.remote.devices.tokens, [])

    def test_strangers_cannot_flood_the_approval_list(self):
        for _ in range(3):
            self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[0], 429)

    def test_per_address_limit_ignores_spoofed_proxy_headers(self):
        self.remote.req_limiter = KeyedLimiter(max_events=2)
        self.remote.requests = PairRequests(max_pending=50)
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request()[0], 429)
        # pretending to be someone else does not reset the limit
        self.assertEqual(self.request(headers={"Cf-Connecting-Ip": "198.51.100.8", "X-Forwarded-For": "1.2.3.4"})[0], 429)

    def test_unknown_ids_and_odd_names(self):
        self.assertEqual(self.status("nope"), {"status": "expired"})
        _, req = self.request("Pixel\x00\x1b[31m" + "x" * 500)
        ua = self.remote.pending_pairs()[0]["ua"]
        self.assertLessEqual(len(ua), 80)
        self.assertNotIn("\x00", ua)
        self.assertNotIn("\x1b", ua)

    def test_extension_and_dashboard_see_the_request(self):
        _, req = self.request()
        self.assertEqual(self.ext("/ext/poll", {"active": True})[1]["pairing"][0]["id"], req["id"])
        st = http(f"http://127.0.0.1:{self.lp}/ui/state")[1]
        self.assertEqual(st["pairing"][0]["words"], req["words"])
        self.assertEqual(self.decide_ui(req["id"], True)[0], 200)
        self.assertEqual(self.status(req["id"])["status"], "approved")

    def decide_ui(self, rid, ok):
        return http(f"http://127.0.0.1:{self.lp}/ui/pair/decide", {"id": rid, "approve": ok}, UI)

    def test_deciding_needs_the_right_credentials(self):
        _, req = self.request()
        self.assertEqual(http(f"http://127.0.0.1:{self.lp}/ui/pair/decide", {"id": req["id"], "approve": True}, {})[0], 403)
        self.assertEqual(http(f"http://127.0.0.1:{self.lp}/remote/pair/decide", {"id": req["id"], "approve": True},
                              {"X-GScript-Token": "wrong", "Origin": "chrome-extension://a"})[0], 401)
        self.assertIn(self.phone("/pair/decide", {"id": req["id"], "approve": True})[0], (401, 404))   # not on the phone server
        self.assertEqual(self.status(req["id"])["status"], "pending")


if __name__ == "__main__":
    unittest.main()
