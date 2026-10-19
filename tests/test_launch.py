import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from gscript import launch

FAKE = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")
ROOT = Path(__file__).resolve().parent.parent


class DiscoveryTests(unittest.TestCase):
    def test_prefers_install_with_studio_exe(self):
        with tempfile.TemporaryDirectory() as home:
            old = {k: os.environ.get(k) for k in ("HOME", "XDG_DATA_HOME", "GSCRIPT_STUDIO_MCP")}
            os.environ["HOME"] = home
            os.environ.pop("XDG_DATA_HOME", None)
            os.environ.pop("GSCRIPT_STUDIO_MCP", None)
            try:
                v = Path(home) / ".local/share/vinegar/versions"
                (v / "v1").mkdir(parents=True)
                (v / "v1/StudioMCP.exe").write_text("x")
                (v / "v1/RobloxStudioBeta.exe").write_text("x")
                time.sleep(0.05)
                (v / "v2").mkdir()
                (v / "v2/StudioMCP.exe").write_text("x")  # newer but leftover (no Studio exe)
                self.assertEqual(launch.find_studio_mcp(), v / "v1/StudioMCP.exe")
            finally:
                for k, val in old.items():
                    os.environ.pop(k, None) if val is None else os.environ.__setitem__(k, val)

    def test_none_found(self):
        with tempfile.TemporaryDirectory() as home:
            old = os.environ.get("HOME")
            os.environ["HOME"] = home
            os.environ.pop("GSCRIPT_STUDIO_MCP", None)
            try:
                self.assertIsNone(launch.find_studio_mcp())
            finally:
                os.environ["HOME"] = old


class ProcTests(unittest.TestCase):
    def test_detects_studio_and_copies_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            proc = Path(d) / "proc"
            winebin = Path(d) / "wine/bin"
            winebin.mkdir(parents=True)
            (winebin / "wine64").write_text("x")
            (winebin / "wine64-preloader").write_text("x")
            (proc / "10").mkdir(parents=True)
            (proc / "10/cmdline").write_bytes(b"/usr/bin/python3\0-m\0gscript.launch\0RobloxStudio.exe\0")
            (proc / "11").mkdir()
            (proc / "11/cmdline").write_bytes(b"/usr/bin/bash\0")
            (proc / "12").mkdir()
            (proc / "12/cmdline").write_bytes(b"Z:\\home\\u\\RobloxStudioBeta.exe\0-app\0")
            (proc / "12/environ").write_bytes(b"WINEPREFIX=/pfx\0DISPLAY=:0\0")
            os.symlink(winebin / "wine64-preloader", proc / "12/exe")
            self.assertEqual(launch.find_studio_process(str(proc)), "12")
            wine, env = launch.studio_runtime("12", str(proc))
            self.assertEqual(wine, str(winebin / "wine64"))
            self.assertEqual(env["WINEPREFIX"], "/pfx")
            self.assertEqual(env["WINEDEBUG"], "-all")

    def test_no_studio_no_spawn(self):
        with tempfile.TemporaryDirectory() as d:
            proc = Path(d) / "proc"
            (proc / "5").mkdir(parents=True)
            (proc / "5/cmdline").write_bytes(b"/usr/bin/vinegar\0run\0")
            self.assertIsNone(launch.find_studio_process(str(proc)))

    def test_try_connect_does_not_spawn_when_studio_closed(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "StudioMCP.exe"
            exe.write_text("x")
            old = os.environ.get("GSCRIPT_STUDIO_MCP"), os.environ.pop("GSCRIPT_MCP_COMMAND", None)
            os.environ["GSCRIPT_STUDIO_MCP"] = str(exe)
            try:
                empty = Path(d) / "proc"
                empty.mkdir()
                client, attempted = launch.try_connect(lambda m: None, proc=str(empty))
                self.assertEqual((client, attempted), (None, False))
            finally:
                os.environ.pop("GSCRIPT_STUDIO_MCP", None)
                if old[0]:
                    os.environ["GSCRIPT_STUDIO_MCP"] = old[0]


class EndToEnd(unittest.TestCase):
    def test_launch_with_fake_studio(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, GSCRIPT_MCP_COMMAND=f"{sys.executable} {FAKE}")
            p = subprocess.Popen([sys.executable, "-u", "-m", "gscript.launch", "--port", "18765"],
                                 cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True)
            try:
                for line in p.stdout:
                    if "Connected to Studio" in line:
                        break

                def call(path, data=None, headers=None):
                    r = urllib.request.Request("http://127.0.0.1:18765" + path,
                                               data=json.dumps(data).encode() if data is not None else None,
                                               headers=headers or {})
                    with urllib.request.urlopen(r) as resp:
                        return json.loads(resp.read())

                token = call("/pair", {}, {"Origin": "chrome-extension://abc"})["token"]   # no code: trusted on first use
                st = call("/status", headers={"X-GScript-Token": token})
                self.assertTrue(st["mcp_alive"])
                self.assertIn("run_luau", st["tools"])
            finally:
                p.terminate()
                p.wait(timeout=5)
                p.stdout.close()


if __name__ == "__main__":
    unittest.main()
