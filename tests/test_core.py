import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

from gscript.bridge import make_server
from gscript.core import Policy, Session
from gscript.mcp_client import McpClient
from gscript.protocol import parse

FAKE = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")
F = "`" * 3


def block(obj, tag="gscript"):
    return f"{F}{tag}\n{json.dumps(obj)}\n{F}"


class ParseTests(unittest.TestCase):
    def test_single_call(self):
        p = parse("Looking.\n" + block({"tool": "get_tree", "args": {"path": "x"}}))
        self.assertEqual(p.calls[0].tool, "get_tree")
        self.assertEqual(p.calls[0].args, {"path": "x"})
        self.assertFalse(p.incomplete)

    def test_incomplete_while_streaming(self):
        p = parse(f'{F}gscript\n{{"tool": "get_tr')
        self.assertTrue(p.incomplete)
        self.assertEqual(p.calls, [])

    def test_trailing_comma_and_smart_quotes(self):
        p = parse(f'{F}gscript\n{{"tool": “get_tree”, "args": {{}},}}\n{F}')
        self.assertEqual(p.calls[0].tool, "get_tree")

    def test_bad_json_reports_error(self):
        p = parse(f"{F}gscript\n{{nope}}\n{F}")
        self.assertEqual(p.calls, [])
        self.assertTrue(p.errors)

    def test_other_fences_ignored(self):
        p = parse(block({"tool": "get_tree"}, tag="json"))
        self.assertEqual(p.calls, [])
        self.assertFalse(p.errors)

    def test_missing_args_defaults(self):
        self.assertEqual(parse(block({"tool": "get_tree"})).calls[0].args, {})


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.client = McpClient([sys.executable, FAKE], timeout=10)
        self.client.start()
        self.s = Session(self.client, Policy(max_steps=3, max_result_chars=1000, reminder_every=2))
        self.s.load_tools()

    def tearDown(self):
        self.client.close()

    def test_tools_and_rules(self):
        self.assertEqual(set(self.s.tools), {"get_tree", "run_luau", "big", "screen_capture"})
        rules = self.s.rules()
        self.assertIn("run_luau(code*: string)", rules)
        self.assertIn("get_tree(path: string)", rules)

    def test_read_only_runs_immediately(self):
        r = self.s.handle_message(block({"tool": "get_tree", "args": {}}))
        self.assertEqual(r["status"], "send")
        self.assertIn("status=ok", r["reply"])
        self.assertIn("Workspace > Baseplate", r["reply"])

    def test_write_needs_approval_then_runs(self):
        r = self.s.handle_message(block({"tool": "run_luau", "args": {"code": "print(1)"}}))
        self.assertEqual(r["status"], "approval")
        self.assertEqual(self.s.steps, 0)
        r2 = self.s.approve(r["pending"]["id"], True)
        self.assertIn("ran: print(1)", r2["reply"])
        self.assertEqual(self.s.steps, 1)

    def test_decline(self):
        r = self.s.handle_message(block({"tool": "run_luau", "args": {"code": "x"}}))
        r2 = self.s.approve(r["pending"]["id"], False)
        self.assertIn("declined", r2["reply"])
        self.assertEqual(self.s.steps, 0)

    def test_stale_approval(self):
        self.assertIn("no longer exists", self.s.approve("nope", True)["reply"])

    def test_tool_error_reported(self):
        self.s.policy.approve_all = True
        r = self.s.handle_message(block({"tool": "run_luau", "args": {"code": "error"}}))
        self.assertIn("status=error", r["reply"])

    def test_unknown_tool(self):
        r = self.s.handle_message(block({"tool": "nuke"}))
        self.assertIn("Unknown tool", r["reply"])

    def test_batch_runs_in_order(self):
        self.s.policy.approve_all = True
        r = self.s.handle_message(block({"tool": "get_tree"}) + "\n" + block({"tool": "run_luau", "args": {"code": "a"}}))
        self.assertEqual(r["count"], 2)
        self.assertEqual(r["reply"].count("[g-script result]"), 2)
        self.assertIn("All steps succeeded", r["reply"])
        self.assertEqual(self.s.steps, 2)

    def test_batch_stops_on_error(self):
        self.s.policy.approve_all = True
        r = self.s.handle_message(block({"tool": "run_luau", "args": {"code": "error"}}) + block({"tool": "get_tree"}))
        self.assertIn("status=skipped", r["reply"])
        self.assertIn("A step failed", r["reply"])
        self.assertEqual(self.s.steps, 1)

    def test_batch_needs_one_approval(self):
        r = self.s.handle_message(block({"tool": "get_tree"}) + block({"tool": "run_luau", "args": {"code": "b"}}))
        self.assertEqual(r["status"], "approval")
        self.assertEqual(len(r["pending"]["calls"]), 2)
        r2 = self.s.approve(r["pending"]["id"], True)
        self.assertEqual(r2["count"], 2)
        self.assertIn("ran: b", r2["reply"])

    def test_array_block(self):
        self.s.policy.approve_all = True
        arr = f"{F}gscript\n" + json.dumps([{"tool": "get_tree"}, {"tool": "get_tree"}]) + f"\n{F}"
        self.assertEqual(self.s.handle_message(arr)["count"], 2)

    def test_too_many_calls(self):
        self.s.policy.max_calls_per_message = 2
        r = self.s.handle_message("".join(block({"tool": "get_tree"}) for _ in range(3)))
        self.assertIn("Too many", r["reply"])
        self.assertEqual(self.s.steps, 0)

    def test_unknown_tool_runs_nothing(self):
        self.s.policy.approve_all = True
        r = self.s.handle_message(block({"tool": "get_tree"}) + block({"tool": "nuke"}))
        self.assertIn("Unknown tool", r["reply"])
        self.assertEqual(self.s.steps, 0)

    def test_plain_text_finishes(self):
        self.assertEqual(self.s.handle_message("All done!")["status"], "finished")

    def test_waiting_when_streaming(self):
        self.assertEqual(self.s.handle_message(f"{F}gscript\n{{")["status"], "waiting")

    def test_truncation(self):
        r = self.s.handle_message(block({"tool": "big"}))
        self.assertIn("[truncated", r["reply"])

    def test_step_limit_and_reset(self):
        for _ in range(3):
            self.s.handle_message(block({"tool": "get_tree"}))
        self.assertEqual(self.s.handle_message(block({"tool": "get_tree"}))["status"], "limit")
        self.s.reset()
        self.assertEqual(self.s.handle_message(block({"tool": "get_tree"}))["status"], "send")

    def test_reminder_every_n(self):
        r1 = self.s.handle_message(block({"tool": "get_tree"}))
        r2 = self.s.handle_message(block({"tool": "get_tree"}))
        self.assertNotIn("reminder", r1["reply"])
        self.assertIn("[g-script reminder]", r2["reply"])


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.client = McpClient([sys.executable, FAKE], timeout=10)
        self.client.start()
        self.s = Session(self.client)
        self.s.load_tools()
        self.server = make_server(self.s, "secret", port=0)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.client.close()

    def req(self, path, data=None, token="secret", origin=None):
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}",
                                   data=json.dumps(data).encode() if data is not None else None)
        if token:
            r.add_header("X-GScript-Token", token)
        if origin:
            r.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_auth(self):
        self.assertEqual(self.req("/status", token=None)[0], 401)
        self.assertEqual(self.req("/status", token="wrong")[0], 401)
        self.assertEqual(self.req("/status")[0], 200)

    def test_origin_check(self):
        self.assertEqual(self.req("/status", origin="https://evil.example")[0], 403)
        self.assertEqual(self.req("/status", origin="chrome-extension://abc")[0], 200)

    def test_rules_and_message(self):
        self.assertIn("g-script rules", self.req("/rules")[1]["rules"])
        code, body = self.req("/message", {"text": block({"tool": "get_tree"})})
        self.assertEqual(code, 200)
        self.assertIn("Workspace", body["reply"])

    def test_pairing(self):
        from gscript.bridge import PairCode
        pc = PairCode()
        self.server.shutdown()
        self.server.server_close()
        self.server = make_server(self.s, "secret", port=0, pair=pc)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        ext = "chrome-extension://abc"
        self.assertEqual(self.req("/pair", {"code": "x"}, token=None, origin=ext)[0], 403)
        self.assertEqual(self.req("/pair", {"code": pc.code}, token=None)[0], 403)  # no Origin
        self.assertEqual(self.req("/pair", {"code": pc.code}, token=None, origin="https://evil.example")[0], 403)
        old = pc.code
        code, body = self.req("/pair", {"code": old}, token=None, origin=ext)
        self.assertEqual((code, body["token"]), (200, "secret"))
        self.assertNotEqual(pc.code, old)  # single use

    def test_approval_flow(self):
        _, body = self.req("/message", {"text": block({"tool": "run_luau", "args": {"code": "1"}})})
        self.assertEqual(body["status"], "approval")
        _, done = self.req("/approve", {"id": body["pending"]["id"], "approve": True})
        self.assertIn("ran: 1", done["reply"])


if __name__ == "__main__":
    unittest.main()
