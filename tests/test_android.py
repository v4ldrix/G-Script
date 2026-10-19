"""The Android project can't be compiled where it was written, so check the mistakes that usually break a build."""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AND = ROOT / "android"
SRC = AND / "app/src/main"
NS = "{http://schemas.android.com/apk/res/android}"


def strip_kotlin(text):
    """Remove comments, strings and char literals so brackets can be counted."""
    out, i, n = [], 0, len(text)
    while i < n:
        two = text[i:i + 2]
        if text.startswith('"""', i):
            j = text.find('"""', i + 3)
            i = n if j < 0 else j + 3
        elif two == "//":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif two == "/*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif text[i] == '"':
            i += 1
            while i < n and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            i += 1
        elif text[i] == "'":
            i += 1
            while i < n and text[i] != "'":
                i += 2 if text[i] == "\\" else 1
            i += 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


class AndroidProjectTests(unittest.TestCase):
    def kt(self):
        return {p.name: p.read_text() for p in (SRC / "java/app/gscript").glob("*.kt")}

    def test_brackets_balance_in_every_kotlin_file(self):
        for name, text in self.kt().items():
            code, stack = strip_kotlin(text), []
            pairs = {")": "(", "]": "[", "}": "{"}
            for ch in code:
                if ch in "([{":
                    stack.append(ch)
                elif ch in pairs:
                    self.assertTrue(stack and stack.pop() == pairs[ch], f"{name}: unmatched {ch}")
            self.assertEqual(stack, [], f"{name}: unclosed {stack}")

    def test_every_file_declares_the_package_and_its_class(self):
        files = self.kt()
        for name, cls in (("MainActivity.kt", "class MainActivity"), ("WatchService.kt", "class WatchService"), ("Prefs.kt", "object Prefs")):
            self.assertIn("package app.gscript", files[name])
            self.assertIn(cls, files[name])

    def test_manifest_matches_the_code_and_resources(self):
        m = ET.parse(SRC / "AndroidManifest.xml").getroot()
        app = m.find("application")
        names = {e.get(NS + "name") for e in list(app.findall("activity")) + list(app.findall("service"))}
        self.assertEqual(names, {".MainActivity", ".WatchService"})
        perms = {e.get(NS + "name") for e in m.findall("uses-permission")}
        for p in ("INTERNET", "POST_NOTIFICATIONS", "FOREGROUND_SERVICE", "FOREGROUND_SERVICE_DATA_SYNC"):
            self.assertIn("android.permission." + p, perms)
        self.assertEqual(app.find("service").get(NS + "foregroundServiceType"), "dataSync")
        for d in ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"):
            self.assertTrue((SRC / f"res/mipmap-{d}/ic_launcher.png").is_file(), d)
        self.assertTrue((SRC / "res/xml/network_security_config.xml").is_file())
        self.assertIn('name="Theme.GScript"', (SRC / "res/values/themes.xml").read_text())
        for f in ("res/values/strings.xml", "res/values/themes.xml", "res/xml/network_security_config.xml", "res/drawable/ic_stat.xml"):
            ET.parse(SRC / f)                                              # well-formed XML

    def test_resources_used_in_code_exist(self):
        for text in self.kt().values():
            for kind, name in re.findall(r"\bR\.(\w+)\.(\w+)", text):
                self.assertTrue(list((SRC / "res").glob(f"{kind}*/{name}.*")), f"R.{kind}.{name} is missing")

    def test_the_phone_page_only_calls_methods_the_app_provides(self):
        html = (ROOT / "gscript/web/app.html").read_text()
        used = set(re.findall(r"\bAND\.(\w+)\(", html))
        provided = set(re.findall(r"@JavascriptInterface\s+fun (\w+)", self.kt()["MainActivity.kt"]))
        self.assertTrue(used, "the page no longer uses the Android bridge")
        self.assertEqual(used - provided, set())
        self.assertIn('"GScriptAndroid"', self.kt()["MainActivity.kt"])

    def test_internal_calls_resolve(self):
        files = self.kt()
        prefs = set(re.findall(r"fun (\w+)\(", files["Prefs.kt"]))
        for name, text in files.items():
            for fn in re.findall(r"\bPrefs\.(\w+)\(", text):
                self.assertIn(fn, prefs, f"{name}: Prefs.{fn}")
            for fn in re.findall(r"\bWatchService\.(\w+)\(", text):
                self.assertIn(fn, {"start", "stop"}, f"{name}: WatchService.{fn}")

    def test_the_service_polls_the_endpoints_the_pc_really_serves(self):
        text = self.kt()["WatchService.kt"]
        self.assertIn("/state?since=", text)
        self.assertIn("X-GScript-Token", text)
        for key in ("events", "last", "studio", "ext", "connected"):
            self.assertIn(f'"{key}"', text)

    def test_gradle_and_workflow(self):
        g = (AND / "app/build.gradle.kts").read_text()
        for needle in ('namespace = "app.gscript"', "compileSdk = 34", "minSdk = 24", "androidx.appcompat:appcompat", "androidx.core:core-ktx"):
            self.assertIn(needle, g)
        wf = (AND / ".github/workflows/android.yml").read_text()
        self.assertIn("assembleDebug", wf)
        self.assertIn("app/build/outputs/apk/debug/app-debug.apk", wf)
        self.assertIn('include(":app")', (AND / "settings.gradle.kts").read_text())


if __name__ == "__main__":
    unittest.main()
