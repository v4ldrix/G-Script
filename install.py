#!/usr/bin/env python3
"""Installs g-script as a normal desktop app:
   Linux   -> app menu entry + icon (no terminal)
   Windows -> Start menu + Desktop shortcut (no console window)
   macOS   -> ~/Applications/g-script.app
Run again to update. Use --uninstall to remove."""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"


def copy_app(dest):
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("gscript", "extension"):
        target = dest / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(HERE / name, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    ico = HERE / "g-script.ico"
    if ico.exists():
        shutil.copy2(ico, dest / "g-script.ico")


def run_quiet(cmd, timeout=30):
    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        pass


# ---------------------------------------------------------------- Linux
def linux_paths():
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share")
    return {
        "data": data, "dest": data / "g-script", "bin": home / ".local" / "bin" / "g-script",
        "desktop": data / "applications" / "g-script.desktop",
        "icon128": data / "icons" / "hicolor" / "128x128" / "apps" / "g-script.png",
        "icon512": data / "icons" / "hicolor" / "512x512" / "apps" / "g-script.png",
    }


def linux_launcher(dest, py):
    return (f'#!/bin/sh\ncd "{dest}" || exit 1\nmkdir -p "$HOME/.gscript"\n'
            f'exec "{py}" -u -m gscript.launch --app "$@" >> "$HOME/.gscript/launch.log" 2>&1\n')


def linux_desktop(launcher, icon):
    return f"""[Desktop Entry]
Type=Application
Version=1.0
Name=g-script
GenericName=AI builder for Roblox Studio
Comment=Build in Roblox Studio with AI chat sites, from your PC or phone
Exec="{launcher}"
Icon={icon}
Terminal=false
Categories=Development;Game;
Keywords=roblox;studio;ai;claude;chatgpt;
StartupNotify=false
"""


def install_linux():
    P = linux_paths()
    copy_app(P["dest"])
    P["bin"].parent.mkdir(parents=True, exist_ok=True)
    P["bin"].write_text(linux_launcher(P["dest"], sys.executable))
    P["bin"].chmod(0o755)
    for key, src in (("icon128", HERE / "extension" / "icons" / "icon128.png"), ("icon512", HERE / "gscript" / "web" / "icon-512.png")):
        P[key].parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, P[key])
    P["desktop"].parent.mkdir(parents=True, exist_ok=True)
    P["desktop"].write_text(linux_desktop(P["bin"], P["icon512"]))
    P["desktop"].chmod(0o755)
    run_quiet(["update-desktop-database", str(P["desktop"].parent)])
    run_quiet(["gtk-update-icon-cache", "-f", "-t", str(P["data"] / "icons" / "hicolor")])
    return P["dest"], "your app menu"


def uninstall_linux():
    P = linux_paths()
    for key in ("desktop", "bin", "icon128", "icon512"):
        P[key].unlink(missing_ok=True)
    shutil.rmtree(P["dest"], ignore_errors=True)
    run_quiet(["update-desktop-database", str(P["desktop"].parent)])


# ---------------------------------------------------------------- Windows
def win_shortcut_script(pyw, dest, ico):
    q = lambda s: str(s).replace("'", "''")
    out = "$w=New-Object -ComObject WScript.Shell;"
    for folder in ("Programs", "Desktop"):
        out += (f"$d=[Environment]::GetFolderPath('{folder}');$s=$w.CreateShortcut((Join-Path $d 'g-script.lnk'));"
                f"$s.TargetPath='{q(pyw)}';$s.Arguments='-m gscript.launch --app';$s.WorkingDirectory='{q(dest)}';"
                f"$s.IconLocation='{q(ico)}';$s.Description='g-script';$s.Save();")
    return out


def win_dest():
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "g-script"


def install_windows():
    dest = win_dest()
    copy_app(dest)
    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        pyw = Path(sys.executable)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                    win_shortcut_script(pyw, dest, dest / "g-script.ico")], check=True, timeout=60)
    return dest, "the Start menu and your Desktop"


def uninstall_windows():
    run_quiet(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
               "foreach($f in 'Programs','Desktop'){Remove-Item (Join-Path ([Environment]::GetFolderPath($f)) 'g-script.lnk') -ErrorAction SilentlyContinue}"], 60)
    shutil.rmtree(win_dest(), ignore_errors=True)


# ---------------------------------------------------------------- macOS
def mac_plist():
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>g-script</string>
  <key>CFBundleDisplayName</key><string>g-script</string>
  <key>CFBundleIdentifier</key><string>app.gscript.desktop</string>
  <key>CFBundleExecutable</key><string>g-script</string>
  <key>CFBundleIconFile</key><string>g-script</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>LSMinimumSystemVersion</key><string>10.13</string>
</dict></plist>
"""


def mac_launcher(py):
    return ('#!/bin/bash\ncd "$(dirname "$0")/../Resources/app" || exit 1\nmkdir -p "$HOME/.gscript"\n'
            f'exec "{py}" -u -m gscript.launch --app >> "$HOME/.gscript/launch.log" 2>&1\n')


def mac_app():
    return Path.home() / "Applications" / "g-script.app"


def install_mac():
    app = mac_app()
    if app.exists():
        shutil.rmtree(app)
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_text(mac_plist())
    exe = app / "Contents" / "MacOS" / "g-script"
    exe.write_text(mac_launcher(sys.executable))
    exe.chmod(0o755)
    icns = HERE / "g-script.icns"
    if icns.exists():
        shutil.copy2(icns, app / "Contents" / "Resources" / "g-script.icns")
    copy_app(app / "Contents" / "Resources" / "app")
    return app / "Contents" / "Resources" / "app", "Launchpad and your Applications folder"


def uninstall_mac():
    shutil.rmtree(mac_app(), ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Install g-script as a desktop app")
    ap.add_argument("--uninstall", action="store_true")
    ap.add_argument("--purge", action="store_true", help="with --uninstall: also delete ~/.gscript (pairing, logs)")
    a = ap.parse_args()
    if sys.version_info < (3, 8):
        sys.exit("g-script needs Python 3.8 or newer.")
    if a.uninstall:
        (uninstall_windows if WIN else uninstall_mac if MAC else uninstall_linux)()
        if a.purge:
            shutil.rmtree(Path.home() / ".gscript", ignore_errors=True)
        print("g-script was removed.")
        return
    dest, where = (install_windows if WIN else install_mac if MAC else install_linux)()
    print(f"g-script is installed. Find it in {where}.")
    print(f"Browser extension folder (load it once at chrome://extensions): {dest / 'extension'}")


if __name__ == "__main__":
    main()
