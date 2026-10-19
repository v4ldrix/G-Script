#!/usr/bin/env bash
# g-script launcher. Double-click it or run ./start.sh. Opens its own terminal window if needed.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
SELF="$PWD/start.sh"

# Not running in a terminal (e.g. double-clicked)? Re-launch inside one.
if [ ! -t 1 ] && [ -z "$GSCRIPT_IN_TERM" ]; then
  export GSCRIPT_IN_TERM=1
  INNER='"$0" "$@"; echo; read -rp "g-script stopped. Press Enter to close... "'
  for t in "$TERMINAL" kitty alacritty foot wezterm konsole gnome-terminal kgx xfce4-terminal tilix terminator lxterminal xterm; do
    [ -n "$t" ] && command -v "$t" >/dev/null 2>&1 || continue
    case "$(basename "$t")" in
      gnome-terminal|kgx) exec "$t" -- bash -c "$INNER" "$SELF" "$@" ;;
      wezterm)            exec "$t" start -- bash -c "$INNER" "$SELF" "$@" ;;
      kitty|foot)         exec "$t" bash -c "$INNER" "$SELF" "$@" ;;
      xfce4-terminal|terminator) exec "$t" -x bash -c "$INNER" "$SELF" "$@" ;;
      *)                  exec "$t" -e bash -c "$INNER" "$SELF" "$@" ;;
    esac
  done
  # no terminal found: run in the background and log to a file
  mkdir -p "$HOME/.gscript"
  echo "No terminal emulator found. Logging to ~/.gscript/launch.log" >&2
  exec python3 -u -m gscript.launch "$@" >>"$HOME/.gscript/launch.log" 2>&1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. On Arch: sudo pacman -S python"
  read -rp "Press Enter to close... "
  exit 1
fi
exec python3 -u -m gscript.launch "$@"
