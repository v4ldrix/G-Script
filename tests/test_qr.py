import json
import shutil
import subprocess
import unittest
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:          # the QR check needs OpenCV; skip where it isn't installed
    cv2 = None

ROOT = Path(__file__).resolve().parent.parent
JS = "const q=require(process.argv[1]).make(process.argv[2]);console.log(JSON.stringify({v:q.version,m:q.modules.map(r=>r.map(b=>b?1:0).join(''))}))"

SAMPLES = [
    "hi",
    "http://192.168.1.20:8766/app#pair=ABCDEFGHJKMN",
    "http://10.0.0.7:8766/app#pair=K7M2PQ9RTX4V",
    "http://192.168.100.200:8766/app#pair=ZZZZZZZZZZZZ",
    "x" * 120,
    "ünïcödé ✓ link",
]


@unittest.skipUnless(cv2 is not None and shutil.which("node"), "needs node and OpenCV")
class QrTests(unittest.TestCase):
    def decoder(self):
        return cv2.QRCodeDetectorAruco() if hasattr(cv2, "QRCodeDetectorAruco") else cv2.QRCodeDetector()

    def encode(self, text):
        out = subprocess.run(["node", "-e", JS, str(ROOT / "gscript/web/qr.js"), text], capture_output=True, text=True, check=True)
        d = json.loads(out.stdout)
        return d["v"], np.array([[int(c) for c in r] for r in d["m"]], dtype=np.uint8)

    def test_codes_scan_back_to_the_same_text(self):
        det = self.decoder()
        for text in SAMPLES:
            v, mat = self.encode(text)
            img = np.kron(np.pad(1 - mat, 4, constant_values=1) * 255, np.ones((8, 8), dtype=np.uint8)).astype(np.uint8)
            got = det.detectAndDecode(img)[0]
            self.assertEqual(got, text, f"v{v} did not scan: {text[:40]!r}")

    def test_real_links_stay_small(self):
        v, _ = self.encode("http://192.168.100.200:8766/app#pair=K7M2PQ9RTX4V")
        self.assertLessEqual(v, 4)

    def test_too_long_text_is_rejected(self):
        r = subprocess.run(["node", "-e", JS, str(ROOT / "gscript/web/qr.js"), "x" * 400], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
