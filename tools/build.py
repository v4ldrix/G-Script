"""Builds g-script-windows.zip, g-script-mac.zip, g-script-linux.zip and g-script-android.zip.

Usage: python tools/build.py [output-folder]      (default: ./dist)"""
import sys
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else SRC / "dist"

README = """
WHAT IT DOES
  Build in Roblox Studio with AI chat sites (Claude, ChatGPT, DeepSeek, Gemini), from your
  computer or from your phone.

SET UP (about 3 minutes, once)
{setup}

USING IT
  1. Open Roblox Studio and a place. Open g-script from {where}.
     A small window shows what is connected. (Closing that window quits g-script.)
  2. On any AI chat page you'll see a g-script bar right above the chat box: press "Start g-script".
     Or click the g-script icon in your browser toolbar, pick an AI, then an action:
     Generate model / animation / UI / script / map, Fix a bug, or Anything else.
     g-script opens that AI in a new chat, gives it the rules and your request, and builds in Studio.
  3. Approve the changes once. The AI replies "Done." Press Ctrl+Z in Studio to undo a build.
  Or open any AI chat yourself and click "Start g-script" in the panel (bottom right).
  If the AI ever forgets the format, click the refresh arrow in the panel to send the rules again.

BUILD FROM YOUR PHONE (optional)
  1. In the g-script window find "Phone" and turn it on. No codes anywhere.
  2. Same Wi-Fi: scan the QR code with your phone camera, or open the link. If your PC asks, compare the
     two words and tap Allow (it also pops up on the g-script bar above your AI chat box).
  3. In your phone browser's menu choose "Add to Home screen", or install the g-script Android app
     (g-script-android.zip). Type what to build, approve changes, see Studio previews.
  Keep an AI chat tab open and visible on your computer, and keep the computer awake. Same Wi-Fi only;
  the link isn't encrypted, so use a network you trust. Every new phone needs your Allow.
{firewall}
TROUBLESHOOTING
  - "Waiting for Roblox Studio": open Studio and a place, and turn on MCP once:
    Assistant > ... > Manage MCP Servers > Enable Studio as MCP Server.
  - The panel says "Offline": the g-script app isn't running. Open it.
  - The bar says "Connecting…" and stays: open the g-script app. If it still stays, click the toolbar icon,
    the gear, then Reconnect. If you installed the extension from two folders, press "Forget the connected
    browser extension" in the g-script window.
  - The panel can't find the chat box or doesn't react: that site changed its layout (tell the developer which one).
  - The g-script window never opens, or something else is wrong: read  {logpath}
  - Can't find Studio's MCP program: set GSCRIPT_STUDIO_MCP to its full path.
{extra_trouble}
UPDATING AND REMOVING
  Update: unzip the new version and run the installer again, then reload the extension at chrome://extensions.
  Remove: {uninstall}

SAFETY
  - Changes to your game ask for your OK (one OK covers a whole batch). Builds set undo points.
  - The computer-side app only listens on your own machine (the phone link only when you turn it on).
    The first browser extension to connect is trusted; every phone must be allowed by you. The phone can
    chat, approve and request previews, nothing more.
  - Not affiliated with Roblox. Use AI chat sites according to their terms.
""".lstrip("\n")

EXT_STEP = """in Chrome / Edge / Brave open chrome://extensions, turn on Developer mode, click "Load unpacked"
     and pick the folder the g-script window shows (it ends in "extension")"""

OS = {
    "windows": dict(
        title="g-script for Windows",
        setup=f"""  1. Install Python 3 (free): open Command Prompt and run   winget install -e --id Python.Python.3.12
     or download it from python.org and tick "Add python.exe to PATH".
  2. Double-click install.bat. It adds g-script to your Start menu and Desktop.
  3. In Roblox Studio turn on MCP once: Assistant > ... > Manage MCP Servers > Enable Studio as MCP Server.
  4. Open g-script from the Start menu. A window opens.
  5. Browser extension (once): {EXT_STEP}. It connects by itself, no code.""",
        where="the Start menu or your Desktop",
        firewall="  Windows may ask to allow Python through the firewall the first time. Allow it on Private networks.\n",
        logpath=r"%USERPROFILE%\.gscript\launch.log",
        extra="  - Python not found: install it (step 1), then run install.bat again.\n"
              "  - start.bat runs g-script in a console window instead, which is handy for debugging.\n",
        uninstall="double-click uninstall.bat."),
    "mac": dict(
        title="g-script for macOS",
        setup=f"""  1. macOS may block downloaded scripts. In Terminal run once:   xattr -dr com.apple.quarantine <this folder>
     (or right-click install.command > Open > Open).
  2. Python 3 is needed. If you don't have it, install.command will offer to install Apple's developer tools.
  3. Double-click install.command. It puts g-script in your Applications folder (Launchpad).
  4. In Roblox Studio turn on MCP once: Assistant > ... > Manage MCP Servers > Enable Studio as MCP Server.
  5. Open g-script from Launchpad. A window opens.
  6. Browser extension (once): {EXT_STEP}. It connects by itself, no code.""",
        where="Launchpad (Applications)",
        firewall="  macOS may ask to allow incoming connections for Python. Click Allow.\n",
        logpath="~/.gscript/launch.log",
        extra="  - \"cannot be opened\": right-click the file > Open, or run the xattr command in step 1.\n"
              "  - start.command runs g-script in a Terminal window instead, which is handy for debugging.\n",
        uninstall="double-click uninstall.command."),
    "linux": dict(
        title="g-script for Linux",
        setup=f"""  1. Python 3:   sudo pacman -S python   (Arch)   /   sudo apt install python3   (Debian, Ubuntu)
  2. Run  ./install.sh  (or double-click it). It adds g-script to your app menu with an icon.
  3. Run Roblox Studio through Vinegar. In Studio turn on MCP once:
     Assistant > ... > Manage MCP Servers > Enable Studio as MCP Server.
  4. Search "g-script" in your app menu and open it. A window opens.
  5. Browser extension (once): {EXT_STEP}. It connects by itself, no code.""",
        where="your app menu",
        firewall="  If a firewall is on, allow port 8766 on your LAN, e.g.  sudo ufw allow from 192.168.0.0/16 to any port 8766\n",
        logpath="~/.gscript/launch.log",
        extra="  - Double-click does nothing: run  chmod +x *.sh  and allow launching in your file manager.\n"
              "  - ./start.sh runs g-script in a terminal instead, which is handy for debugging; it lists exactly\n"
              "    what it tried to launch Studio's MCP program. Flatpak Vinegar may need GSCRIPT_MCP_COMMAND set.\n",
        uninstall="run ./uninstall.sh (add --purge to also delete pairing data)."),
}

BAT_START = r"""@echo off
setlocal
cd /d "%~dp0"
title g-script
set "PY="
py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo.
  echo  Python 3 was not found.
  echo  Install it once with:  winget install -e --id Python.Python.3.12
  echo  or from https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
  echo.
  pause
  exit /b 1
)
%PY% -u -m gscript.launch %*
echo.
echo  g-script stopped.
pause
"""

MAC_START = """#!/bin/bash
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is needed. A dialog may offer to install Apple's developer tools: accept it,"
  echo "wait for it to finish, then double-click start.command again."
  xcode-select --install 2>/dev/null
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi
python3 -u -m gscript.launch "$@"
echo
read -n 1 -s -r -p "g-script stopped. Press any key to close... "
"""

MAC_UNINSTALL = """#!/bin/bash
cd "$(dirname "$0")" || exit 1
python3 install.py --uninstall "$@"
echo
read -n 1 -s -r -p "Press any key to close... "
"""


def add(z, name, data, mode=0o644):
    if isinstance(data, str):
        data = data.encode("utf-8")
    zi = zipfile.ZipInfo(name, date_time=(2026, 10, 17, 12, 0, 0))
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = (0o100000 | mode) << 16
    z.writestr(zi, data)


def tree(z, root, folder):
    for p in sorted((SRC / folder).rglob("*")):
        if p.is_dir() or "__pycache__" in p.parts or p.suffix == ".pyc":
            continue
        add(z, f"{root}/{p.relative_to(SRC).as_posix()}", p.read_bytes())


def crlf(s):
    return s.replace("\r\n", "\n").replace("\n", "\r\n")


def build(osname):
    o = OS[osname]
    root = f"g-script-{osname}"
    out = OUT / f"{root}.zip"
    out.unlink(missing_ok=True)
    text = o["title"] + "\n" + "=" * len(o["title"]) + "\n\n" + README.format(
        setup=o["setup"], where=o["where"], firewall=o["firewall"], logpath=o["logpath"],
        extra_trouble=o["extra"], uninstall=o["uninstall"])
    with zipfile.ZipFile(out, "w") as z:
        tree(z, root, "gscript")
        tree(z, root, "extension")
        add(z, f"{root}/install.py", (SRC / "install.py").read_text())
        add(z, f"{root}/README.txt", crlf(text) if osname == "windows" else text)
        if osname == "windows":
            for n in ("install.bat", "uninstall.bat"):
                add(z, f"{root}/{n}", crlf((SRC / n).read_text()))
            add(z, f"{root}/start.bat", crlf(BAT_START))
            add(z, f"{root}/g-script.ico", (SRC / "g-script.ico").read_bytes())
        elif osname == "mac":
            add(z, f"{root}/install.command", (SRC / "install.command").read_text(), 0o755)
            add(z, f"{root}/uninstall.command", MAC_UNINSTALL, 0o755)
            add(z, f"{root}/start.command", MAC_START, 0o755)
            add(z, f"{root}/g-script.icns", (SRC / "g-script.icns").read_bytes())
        else:
            for n in ("install.sh", "uninstall.sh", "start.sh", "_term.sh"):
                add(z, f"{root}/{n}", (SRC / n).read_text(), 0o755)
    return out


def build_android():
    root = "g-script-android"
    out = OUT / f"{root}.zip"
    out.unlink(missing_ok=True)
    skip = {"build", ".gradle", ".idea"}
    with zipfile.ZipFile(out, "w") as z:
        for p in sorted((SRC / "android").rglob("*")):
            rel = p.relative_to(SRC / "android")
            if p.is_dir() or skip & set(rel.parts) or p.name in ("local.properties",) or p.suffix == ".iml":
                continue
            add(z, f"{root}/{rel.as_posix()}", p.read_bytes())
    return out


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name in OS:
        p = build(name)
        print(p.name, p.stat().st_size // 1024, "KB")
    p = build_android()
    print(p.name, p.stat().st_size // 1024, "KB")
