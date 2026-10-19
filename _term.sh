# Sourced by install.sh / uninstall.sh. Usage: gs_in_terminal "$SELF" "$@"
# If there is no terminal (double-clicked), re-run the script inside one and keep it open at the end.
gs_in_terminal() {
  if [ -t 1 ] || [ -n "$GSCRIPT_IN_TERM" ]; then return 0; fi
  export GSCRIPT_IN_TERM=1
  local INNER='"$0" "$@"; echo; read -rp "Press Enter to close... "'
  local t
  for t in "$TERMINAL" kitty alacritty foot wezterm konsole gnome-terminal kgx xfce4-terminal tilix terminator lxterminal xterm; do
    [ -n "$t" ] && command -v "$t" >/dev/null 2>&1 || continue
    case "$(basename "$t")" in
      gnome-terminal|kgx) exec "$t" -- bash -c "$INNER" "$@" ;;
      wezterm)            exec "$t" start -- bash -c "$INNER" "$@" ;;
      kitty|foot)         exec "$t" bash -c "$INNER" "$@" ;;
      xfce4-terminal|terminator) exec "$t" -x bash -c "$INNER" "$@" ;;
      *)                  exec "$t" -e bash -c "$INNER" "$@" ;;
    esac
  done
  return 0   # no terminal emulator found: carry on without one
}
