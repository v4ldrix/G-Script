import time
import unittest

from gscript import access
from gscript.access import PairLimiter
from tests.test_phone import PhoneBase, http


class RemoteSecurityTests(PhoneBase):
    def pair(self, code, headers=None):
        return http(f"http://127.0.0.1:{self.rp}/pair", {"code": code}, headers or {})

    def test_qr_secret_pairs_once_and_rotates(self):
        s = self.remote.secret
        spaced = "-".join(s[i:i + 4] for i in range(0, 12, 4)).lower()       # how a person might type it
        code, body = self.pair(spaced)
        self.assertEqual(code, 200)
        self.assertTrue(self.remote.devices.check(body["token"]))
        self.assertNotEqual(self.remote.secret, s)                          # single use
        self.assertEqual(self.pair(s)[0], 403)

    def test_short_code_still_works(self):
        self.assertEqual(self.pair(self.remote.pair.code)[0], 200)

    def test_proxy_headers_change_nothing(self):
        # there is no proxy, so these headers must not unlock or block anything
        self.assertEqual(self.pair("000000", {"Cf-Connecting-Ip": "1.2.3.4", "X-Forwarded-For": "5.6.7.8"})[0], 403)
        self.assertEqual(self.pair(self.remote.pair.code, {"Cf-Ray": "abc"})[0], 200)

    def test_lockout_after_too_many_wrong_tries(self):
        for _ in range(5):
            self.assertEqual(self.pair("WRONG1")[0], 403)
        code, body = self.pair(self.remote.secret)                           # even the right one is refused now
        self.assertEqual(code, 429)
        self.assertIn("Too many", body["error"])

    def test_lockout_ends(self):
        self.remote.limiter = PairLimiter(max_fails=2, window=1.0)
        self.pair("AAAAAA"); self.pair("BBBBBB")
        self.assertEqual(self.pair(self.remote.pair.code)[0], 429)
        time.sleep(1.2)
        self.assertEqual(self.pair(self.remote.pair.code)[0], 200)

    def test_odd_input_is_just_a_wrong_code(self):
        for bad in ("ＡＢＣＤＥＦＧＨＪＫＭＮ", "é" * 12, "", "   ", "A" * 5000):
            self.assertEqual(self.pair(bad)[0], 403, bad[:10])

    def test_status_is_wifi_only(self):
        st = self.remote.status()
        self.assertTrue(st["lan"]["link"].endswith("/app#pair=" + st["secret"]))
        self.assertNotIn("tunnel", st)
        self.assertNotIn("tailscale", st)

    def test_reset_rotates_the_secret(self):
        s = self.remote.secret
        self.remote.reset_devices()
        self.assertNotEqual(self.remote.secret, s)

    def test_manifest_and_no_service_worker(self):
        manifest = http(f"http://127.0.0.1:{self.rp}/manifest.webmanifest")[1]
        self.assertEqual(manifest["start_url"], "/app")
        self.assertEqual(self.phone("/sw.js")[0], 401)       # not served any more (falls through to "needs a token")

    def test_the_internet_features_are_gone(self):
        ui = {"X-GScript-UI": "1", "Content-Type": "application/json"}
        self.assertEqual(http(f"http://127.0.0.1:{self.lp}/ui/tunnel", {"enable": True}, ui)[0], 404)
        for name in ("Tunnel", "tailscale_ip", "tailscale_ip_cached"):
            self.assertFalse(hasattr(access, name), name)

    def test_qr_script_is_served_to_the_dashboard(self):
        code, body = http(f"http://127.0.0.1:{self.lp}/ui/qr.js")
        self.assertEqual(code, 200)
        self.assertIn(b"GS_QR", body)


if __name__ == "__main__":
    unittest.main()
