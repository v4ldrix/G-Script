# g-script

**Build in Roblox Studio with the AI chat sites you already use** (Claude, ChatGPT, DeepSeek, Gemini), from your
computer or your phone. g-script connects the chat to Roblox Studio's built-in MCP server, so the AI can really
create models, UI, scripts and maps in your open place, and tells you "Done." when it has.

```
AI chat site  →  browser extension  →  g-script app (on your PC)  →  Roblox Studio (MCP)
                                              ↑
                                  your phone (same Wi-Fi)
```

## Features
- **One-message builds:** the AI plans, sends every step at once, you approve once, it says Done. Builds set undo points.
- **A bar above the chat box** with Start / Stop and settings, plus a toolbar menu with **Generate model, animation,
  UI, script, map**, **Fix a bug** and an AI switcher.
- **Real desktop app** on Windows, macOS and Linux (app menu / Start menu / Launchpad), no terminal.
- **No pairing codes:** the extension connects by itself; phones are approved with one click on the PC.
- **Phone app** (web page or Android app) on the same Wi-Fi: chat, approve, see Studio previews. QR code included.
- Safe by default: localhost-only bridge, approval for every change, rate-limited pairing. See [SECURITY.md](SECURITY.md).

## Install
Download your system's zip from the [Releases](../../releases) page and follow the `README.txt` inside:
`g-script-windows.zip`, `g-script-mac.zip`, `g-script-linux.zip`, and `g-script.apk` for Android.

Short version: install Python 3 → run the installer → open **g-script** from your apps → load the `extension` folder once
at `chrome://extensions` (Developer mode → Load unpacked) → open an AI chat and press **Start g-script**.

## Repository layout
| Path | What |
|---|---|
| `gscript/` | the PC app: launcher, MCP client, agent loop, phone server, dashboard (Python, no dependencies) |
| `extension/` | the Chromium extension (Manifest V3) |
| `android/` | the Android app (Kotlin WebView + background alerts) |
| `install.py`, `install.*`, `start.*` | desktop installers/launchers |
| `tools/build.py` | builds the release zips (`python tools/build.py`) |
| `tests/` | `python -m unittest discover -s tests -t .` (also needs Node; QR tests use OpenCV if present) |

## Status
Tested against a real machine, macos yet to be tested

Roblox Studio's MCP launch details on Linux (Vinegar/Wine) are the most likely thing to need a tweak:
the terminal (`./start.sh`) lists exactly what it tried.

## Disclaimer
Not affiliated with or endorsed by Roblox, Anthropic, OpenAI, DeepSeek or Google. Automating web chat pages may conflict
with their terms of service; use at your own risk.

## License
MIT, see [LICENSE](LICENSE).
