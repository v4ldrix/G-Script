"""One-command start (Windows, macOS, Linux): finds Studio's MCP server, starts the bridge,
reconnects if Studio restarts, optionally serves the phone app."""
import argparse
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from . import __version__
from .bridge import load_token, make_server
from .core import Policy, Session
from .hub import Hub
from .mcp_client import McpClient, McpError, NullClient
from .pairing import ExtTrust, PairCode
from .remote import Remote

FLATPAK_ID = "org.vinegarhq.Vinegar"
STUDIO_EXES = ("RobloxStudioBeta.exe", "RobloxStudio.exe")
WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"


# ---------------------------------------------------------------- finding StudioMCP
def _pick(paths, siblings):
    """Newest StudioMCP next to a real Studio exe (skips leftovers of old versions)."""
    paired, orphans = [], []
    for exe in paths:
        ok = any((exe.parent / n).is_file() for n in siblings)
        (paired if ok else orphans).append(exe)
    pick = paired or orphans
    return max(pick, key=lambda p: p.stat().st_mtime) if pick else None


def _find_windows(env=None):
    env = env or os.environ
    paths = []
    for var in ("LOCALAPPDATA", "ProgramFiles(x86)", "ProgramFiles"):
        base = env.get(var)
        if base:
            paths += list(Path(base, "Roblox", "Versions").glob("*/StudioMCP.exe"))
    return _pick(paths, STUDIO_EXES)


def _find_mac(roots=None):
    roots = roots or [Path("/Applications"), Path.home() / "Applications"]
    paths = []
    for r in roots:
        paths += list(r.glob("RobloxStudio*.app/Contents/MacOS/StudioMCP"))
    return _pick(paths, ("RobloxStudio",))


def vinegar_roots():
    home = Path.home()
    xdg = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    roots = [home / ".var" / "app" / FLATPAK_ID / "data" / "vinegar", xdg / "vinegar"]
    return [r for r in roots if r.is_dir()]


def _find_linux():
    pats = []
    for r in vinegar_roots():
        pats += [r.glob("versions/*/StudioMCP.exe"),
                 r.glob("prefixes/*/drive_c/users/*/AppData/Local/Roblox/Versions/*/StudioMCP.exe")]
    pats.append((Path.home() / ".wine").glob("drive_c/users/*/AppData/Local/Roblox/Versions/*/StudioMCP.exe"))
    paired, orphans = [], []
    for it in pats:
        for exe in it:
            ok = any((exe.parent / n).is_file() for n in STUDIO_EXES)
            (paired if ok else orphans).append(exe)
    if not paired and not orphans:
        for r in vinegar_roots():
            orphans += list(r.rglob("StudioMCP.exe"))
    pick = paired or orphans
    return max(pick, key=lambda p: p.stat().st_mtime) if pick else None


def find_studio_mcp():
    override = os.environ.get("GSCRIPT_STUDIO_MCP")
    if override and Path(override).is_file():
        return Path(override)
    if WIN:
        return _find_windows()
    if MAC:
        return _find_mac()
    return _find_linux()


# ---------------------------------------------------------------- is Studio running?
def find_studio_process(proc="/proc"):
    """Linux: PID of a running Studio (Wine process), or None. Spawns nothing."""
    me = str(os.getpid())
    for pid in sorted(os.listdir(proc)):
        if not pid.isdigit() or pid == me:
            continue
        try:
            cmd = Path(proc, pid, "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "ignore")
        except OSError:
            continue
        low = cmd.lower()
        if "robloxstudio" in low and ".exe" in low and "gscript" not in low:
            return pid
    return None


def studio_running(proc="/proc"):
    try:
        if WIN:
            out = subprocess.run(["tasklist", "/NH", "/FO", "CSV"], capture_output=True, text=True,
                                 creationflags=0x08000000).stdout
            return "robloxstudiobeta.exe" in out.lower()
        if MAC:
            return subprocess.run(["pgrep", "-f", "RobloxStudio.app"], capture_output=True).returncode == 0
    except OSError:
        return False
    return find_studio_process(proc) is not None


def studio_runtime(pid, proc="/proc"):
    """Linux: (wine_path, env) copied from the running Studio so we use the same Wine and prefix."""
    env = {}
    try:
        raw = Path(proc, pid, "environ").read_bytes().split(b"\0")
        env = dict(x.decode("utf-8", "ignore").split("=", 1) for x in raw if b"=" in x)
    except OSError:
        env = dict(os.environ)
    env["WINEDEBUG"] = "-all"
    wine = None
    try:
        d = Path(os.readlink(f"{proc}/{pid}/exe")).parent
        wine = next((str(d / n) for n in ("wine64", "wine") if (d / n).is_file()), None)
    except OSError:
        pass
    return wine or shutil.which("wine"), env


# ---------------------------------------------------------------- connecting
def _attempt(label, cmd, env, log, timeout):
    log(f"Trying: {label}")
    client = McpClient(cmd, env=env, timeout=timeout)
    try:
        client.start()
        tools = client.list_tools()
    except McpError as e:
        tail = " | ".join(list(client.stderr_tail)[-2:])
        log(f"  failed: {e}" + (f"  [{tail}]" if tail else ""))
        client.close()
        return None
    if tools:
        return client
    log("  connected but Studio has no tools yet (is a place open and MCP enabled?)")
    client.close()
    return None


NOT_FOUND = {
    "win": "Could not find StudioMCP.exe. Install or update Roblox Studio and enable MCP "
           "(Assistant > ... > Manage MCP Servers). Or set GSCRIPT_STUDIO_MCP=C:\\path\\StudioMCP.exe",
    "mac": "Could not find StudioMCP in /Applications/RobloxStudio.app. Update Roblox Studio and enable MCP "
           "(Assistant > ... > Manage MCP Servers). Or set GSCRIPT_STUDIO_MCP=/path/to/StudioMCP",
    "linux": "Could not find StudioMCP.exe. Open Roblox Studio once (Vinegar) and enable 'Studio as MCP "
             "Server' (Assistant > ... > Manage MCP Servers). Or set GSCRIPT_STUDIO_MCP=/path/to/StudioMCP.exe",
}


def try_connect(log, timeout=15, proc="/proc"):
    """Returns (client or None, attempted). Only launches anything while Studio is running."""
    override = os.environ.get("GSCRIPT_MCP_COMMAND")
    if override:
        return _attempt("GSCRIPT_MCP_COMMAND", shlex.split(override), dict(os.environ), log, timeout), True
    exe = find_studio_mcp()
    if not exe:
        log(NOT_FOUND["win" if WIN else "mac" if MAC else "linux"])
        return None, False
    if not studio_running(proc):
        log("Waiting for Roblox Studio to be open...")
        return None, False
    if WIN or MAC:
        for args in (["--stdio"], []):
            client = _attempt(" ".join([exe.name] + args), [str(exe)] + args, dict(os.environ), log, timeout)
            if client:
                return client, True
        return None, True
    pid = find_studio_process(proc)
    wine, env = studio_runtime(pid, proc)
    if not wine:
        log("Studio is running but I can't find its Wine (Flatpak Vinegar?). "
            'Set GSCRIPT_MCP_COMMAND="wine /path/to/StudioMCP.exe --stdio" (use your Wine and WINEPREFIX).')
        return None, False
    log(f"Studio is running. Using {wine} with {exe}")
    for args in (["--stdio"], []):
        client = _attempt(f"wine {' '.join(args)}".strip(), [wine, str(exe)] + args, env, log, timeout)
        if client:
            return client, True
    return None, True


# ---------------------------------------------------------------- app window / desktop niceties
def _single_instance():
    """Hold a lock for the life of the process so two launchers can't run at once."""
    d = Path.home() / ".gscript"
    d.mkdir(parents=True, exist_ok=True)
    f = open(d / "lock", "w")
    try:
        if WIN:
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def _browser_candidates():
    """Chromium-family browsers, which can open a page as a chromeless app window."""
    if WIN:
        bases = [os.environ.get(v) for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        rels = ["Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe",
                "BraveSoftware/Brave-Browser/Application/brave.exe"]
        return [str(Path(b) / r) for b in bases if b for r in rels if (Path(b) / r).is_file()]
    if MAC:
        apps = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Chromium.app/Contents/MacOS/Chromium"]
        return [a for a in apps if Path(a).is_file()]
    names = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome", "brave",
             "brave-browser", "microsoft-edge-stable", "microsoft-edge", "vivaldi")
    return [p for p in (shutil.which(n) for n in names) if p]


def open_app_window(url):
    """Open the dashboard in its own window (like a normal app), else in the default browser."""
    if os.environ.get("GSCRIPT_NO_WINDOW"):
        return False
    for exe in _browser_candidates():
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=480,840"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            continue
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def _alert(msg):
    """Tell a user who launched us from the app menu (there is no terminal to print to)."""
    msg = str(msg).replace('"', "'")
    try:
        if WIN:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "g-script", 0x10)
        elif MAC:
            subprocess.run(["osascript", "-e", f'display dialog "{msg}" with title "g-script" buttons {{"OK"}}'], timeout=60)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", "-a", "g-script", "g-script", msg], timeout=10)
        elif shutil.which("zenity"):
            subprocess.run(["zenity", "--error", "--title=g-script", f"--text={msg}"], timeout=60)
    except Exception:
        pass


def _fatal(msg, app):
    print(f"[g-script] {msg}", file=sys.stderr, flush=True)
    if app:
        _alert(msg)
    sys.exit(1)


def _redirect_if_headless():
    """pythonw (Windows app shortcut) has no stdout: send output to a log file instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    d = Path.home() / ".gscript"
    d.mkdir(parents=True, exist_ok=True)
    f = open(d / "launch.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = f


def _trim_log():
    p = Path.home() / ".gscript" / "launch.log"
    try:
        if p.stat().st_size > 1_000_000:
            os.truncate(p, 0)
    except OSError:
        pass


def _open_existing():
    """g-script is already running: just bring its window back."""
    try:
        port = int((Path.home() / ".gscript" / "port").read_text().strip())
    except (OSError, ValueError):
        port = 8765
    open_app_window(f"http://127.0.0.1:{port}/ui")


def _style():
    """UTF-8 output everywhere, ANSI colors when it's a terminal."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    on = bool(sys.stdout) and sys.stdout.isatty()
    if WIN and on:
        os.system("")  # enables ANSI escape handling on Windows 10+
    return (lambda t, c: f"\033[{c}m{t}\033[0m" if on else t)


def main(argv=None):
    ap = argparse.ArgumentParser(description="g-script launcher")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--app", action="store_true",
                    help="desktop app mode: open the dashboard window and quit when it is closed")
    ap.add_argument("--phone", action="store_true", help="turn on the phone app now")
    ap.add_argument("--phone-port", type=int, default=8766)
    ap.add_argument("--project-rules", help="file with extra rules for the AI")
    ap.add_argument("--approve-all", action="store_true")
    ap.add_argument("--max-steps", type=int, default=60)
    ap.add_argument("--read-only-tools", default=os.environ.get("GSCRIPT_READ_ONLY", ""),
                    help="comma-separated tool names that never need approval")
    a = ap.parse_args(argv)
    _redirect_if_headless()
    col = _style()
    hub = Hub()

    def log(msg):
        print(f"[g-script] {msg}", flush=True)
        hub.log(msg)

    lock = _single_instance()
    if lock is None:
        if a.app:
            _open_existing()
            return
        sys.exit("[g-script] Already running in another window. Close that one first.")
    if a.app:
        _trim_log()
    state_dir = Path.home() / ".gscript"
    token = load_token(state_dir / "token")
    pair = PairCode(on_rotate=lambda c: log(f"New pairing code: {c}"))
    policy = Policy(read_only=frozenset(filter(None, a.read_only_tools.split(","))),
                    approve_all=a.approve_all, max_steps=a.max_steps)
    rules = Path(a.project_rules).read_text() if a.project_rules else ""
    session = Session(NullClient(), policy, rules)
    remote = Remote(hub, session, port=a.phone_port)
    trust = ExtTrust(state_dir / "ext_id", on_event=hub.log)
    try:
        server = make_server(session, token, port=a.port, pair=pair, hub=hub, remote=remote, trust=trust)
    except OSError as e:
        _fatal(f"Cannot listen on port {a.port}: {e}. Is another program using it?", a.app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        (state_dir / "port").write_text(str(a.port))
    except OSError:
        pass
    hub.app_mode = a.app
    if a.app:
        hub.ui_seen = time.time() + float(os.environ.get("GSCRIPT_UI_GRACE", "60"))   # grace while the window opens

    phone_note = ""
    if a.phone or remote.saved_enabled():
        try:
            remote.enable()
            phone_note = f" Phone app:  {remote.url()}   (you approve it here, no code)"
        except OSError as e:
            log(f"Phone app could not start: {e}")

    dash = f"http://127.0.0.1:{a.port}/ui"
    print(col("=" * 58, "35"))
    print(col(f" g-script {__version__}", "1;36") + f"   bridge running on http://127.0.0.1:{a.port}")
    print(" Browser extension: connects by itself, no code needed")
    print(f" Dashboard: {dash}")
    if phone_note:
        print(phone_note)
    print(col("=" * 58, "35"), flush=True)
    hub.log(f"g-script {__version__} started")
    if a.app and not open_app_window(dash):
        log(f"Open {dash} in your browser to see the dashboard.")

    def should_quit():
        if hub.quit:
            return "Quit from the dashboard."
        if a.app and time.time() - hub.ui_seen > float(os.environ.get("GSCRIPT_UI_STALE", "25")):
            return "Window closed."
        return None

    def wait(seconds):
        end = time.time() + seconds
        while time.time() < end:
            if should_quit():
                return True
            time.sleep(0.4)
        return False

    client, last, delay = None, None, 3

    def quiet_log(msg):
        nonlocal last
        if msg != last:
            log(msg)
            last = msg

    try:
        while not should_quit():
            if client is not None and not client.alive:
                log("Lost connection to Studio. Reconnecting...")
                client, session.client, session.tools = None, NullClient(), {}
            if client is None:
                client, attempted = try_connect(quiet_log)
                if client:
                    delay = 3
                    session.client = client
                    names = session.load_tools()
                    log(col("Connected to Studio.", "1;32") + f" Tools: {', '.join(names)}")
                    need = [n for n in names if not session.is_read_only(n)]
                    if need:
                        log(f"Need approval: {', '.join(need)}  (mark safe ones with GSCRIPT_READ_ONLY=a,b)")
                    last = None
                else:
                    # back off after real launch failures so we never spam processes
                    delay = min(delay * 2, 60) if attempted else 3
                    if wait(delay):
                        break
                    continue
            if wait(2):
                break
    except KeyboardInterrupt:
        pass
    finally:
        reason = should_quit()
        if reason:
            log(f"Stopping. {reason}")
        if client:
            client.close()
        remote.close()
        server.shutdown()
        try:
            (state_dir / "port").unlink()
        except OSError:
            pass


if __name__ == "__main__":
    main()
