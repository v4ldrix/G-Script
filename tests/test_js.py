import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class JsTests(unittest.TestCase):
    def run_js(self, name):
        r = subprocess.run(["node", str(ROOT / "tests" / "js" / name)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_loop_logic(self):
        self.run_js("test_loop.js")

    def test_adapters(self):
        self.run_js("test_adapters.js")

    def test_all_scripts_parse(self):
        for f in (ROOT / "extension").glob("*.js"):
            r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{f.name}: {r.stderr}")


if __name__ == "__main__":
    unittest.main()
