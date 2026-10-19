import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

import install

ROOT = Path(__file__).resolve().parent.parent
FAKE = os.path.join(os.path.dirname(__file__), "fake_mcp_server.py")


def get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read())


def post(url, data=None):
    req = urllib.request.Request(url, data=json.dumps(data or {}).encode(), method="POST",
                                 headers={"X-GScript-UI": "1", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read())


def wait_for(fn, seconds=15):
    end = time.time() + seconds
    while time.time() < end:
        try:
            v = fn()
            if v:
                return v
        except Exception:
            pass
        time.sleep(0.2)
    return None


class TemplateTests(unittest.TestCase):
    def test_linux_desktop_entry_is_a_normal_app(self):
        d = install.linux_desktop(Path("/home/u/.local/bin/g-script"), Path("/home/u/icon.png"))
        for line in ("Name=g-script", "Type=Application", "Terminal=false", 'Exec="/home/u/.local/bin/g-script"', "Icon=/home/u/icon.png"):
            self.assertIn(line, d)

    def test_mac_bundle_files(self):
        self.assertIn("<key>CFBundleExecutable</key><string>g-script</string>", install.mac_plist())
        self.assertIn("gscript.launch --app", install.mac_launcher("/usr/bin/python3"))

    def test_windows_shortcuts_use_no_console_and_app_flag(self):
        ps = install.win_shortcut_script(r"C:\Py\pythonw.exe", r"C:\Users\me\AppData\Local\g-script", r"C:\x\g-script.ico")
        self.assertIn("pythonw.exe", ps)
        self.assertIn("-m gscript.launch --app", ps)
        self.assertIn("'Programs'", ps)
        self.assertIn("'Desktop'", ps)
        self.assertIn("TargetPath='it''s'", install.win_shortcut_script("it's", "d", "i"))  # quotes are escaped


class LinuxInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = dict(os.environ, HOME=str(self.home), XDG_DATA_HOME=str(self.home / "data"),
                        GSCRIPT_NO_WINDOW="1", GSCRIPT_MCP_COMMAND=f"{sys.executable} {FAKE}")
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
            p.wait(timeout=10)
            p.stdout and p.stdout.close()
        self.tmp.cleanup()

    def run_install(self, *args):
        r = subprocess.run([sys.executable, "install.py", *args], cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def launch(self, *args, **env):
        p = subprocess.Popen([str(self.home / ".local/bin/g-script"), *args], env={**self.env, **env},
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.procs.append(p)
        return p

    def test_install_creates_a_real_app_menu_entry(self):
        out = self.run_install()
        data = self.home / "data"
        self.assertIn("app menu", out)
        self.assertTrue((data / "g-script/gscript/launch.py").is_file())
        self.assertTrue((data / "g-script/gscript/web/app.html").is_file())
        self.assertTrue((data / "g-script/extension/manifest.json").is_file())
        launcher = self.home / ".local/bin/g-script"
        self.assertTrue(os.access(launcher, os.X_OK))
        desktop = (data / "applications/g-script.desktop").read_text()
        self.assertIn("Terminal=false", desktop)
        self.assertIn(str(launcher), desktop)
        self.assertTrue((data / "icons/hicolor/512x512/apps/g-script.png").is_file())
        v = subprocess.run(["desktop-file-validate", str(data / "applications/g-script.desktop")], capture_output=True, text=True) \
            if subprocess.run(["which", "desktop-file-validate"], capture_output=True).returncode == 0 else None
        if v:
            self.assertEqual(v.returncode, 0, v.stdout + v.stderr)

    def test_installed_app_runs_serves_dashboard_and_quits(self):
        self.run_install()
        p = self.launch("--port", "18971", "--phone-port", "18972")
        st = wait_for(lambda: (lambda s: s if s["studio"]["connected"] else None)(get("http://127.0.0.1:18971/ui/state")))
        self.assertIsNotNone(st, "installed app never connected to (fake) Studio")
        self.assertTrue(st["extension_path"].endswith("g-script/extension"))
        # launching it again must not start a second copy
        second = self.launch("--port", "18971")
        self.assertEqual(second.wait(timeout=15), 0)
        post("http://127.0.0.1:18971/ui/quit")
        self.assertEqual(p.wait(timeout=15), 0)
        log = (self.home / ".gscript/launch.log").read_text()
        self.assertIn("Connected to Studio", log)
        self.assertIn("Quit from the dashboard", log)

    def test_closing_the_window_quits_the_app(self):
        self.run_install()
        p = self.launch("--port", "18973", "--phone-port", "18974", GSCRIPT_UI_GRACE="1", GSCRIPT_UI_STALE="2")
        self.assertIsNotNone(wait_for(lambda: get("http://127.0.0.1:18973/ui/state")))
        t0 = time.time()
        self.assertEqual(p.wait(timeout=20), 0)                      # nobody pings => it quits by itself
        self.assertLess(time.time() - t0, 15)
        self.assertIn("Window closed", (self.home / ".gscript/launch.log").read_text())

    def test_pings_keep_it_alive(self):
        self.run_install()
        p = self.launch("--port", "18975", "--phone-port", "18976", GSCRIPT_UI_GRACE="1", GSCRIPT_UI_STALE="2")
        self.assertIsNotNone(wait_for(lambda: get("http://127.0.0.1:18975/ui/state")))
        for _ in range(12):
            post("http://127.0.0.1:18975/ui/ping")
            time.sleep(0.5)
            self.assertIsNone(p.poll(), "quit even though the window was still pinging")
        post("http://127.0.0.1:18975/ui/quit")
        self.assertEqual(p.wait(timeout=15), 0)

    def test_uninstall_removes_everything(self):
        self.run_install()
        self.run_install("--uninstall")
        data = self.home / "data"
        self.assertFalse((data / "applications/g-script.desktop").exists())
        self.assertFalse((self.home / ".local/bin/g-script").exists())
        self.assertFalse((data / "g-script").exists())


if __name__ == "__main__":
    unittest.main()
