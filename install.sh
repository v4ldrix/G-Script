#!/usr/bin/env bash
# Installs g-script into your app menu (opens as a normal app, no terminal). Double-click or run ./install.sh
cd "$(dirname "$(readlink -f "$0")")" || exit 1
. ./_term.sh
gs_in_terminal "$PWD/install.sh" "$@"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is needed first:  sudo pacman -S python   (Arch)  /  sudo apt install python3  (Debian, Ubuntu)"
  exit 1
fi
python3 install.py "$@"
