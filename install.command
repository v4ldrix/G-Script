#!/bin/bash
# Installs g-script into ~/Applications (Launchpad). Double-click to run.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is needed. A dialog may offer to install Apple's developer tools: accept it,"
  echo "wait for it to finish, then double-click install.command again."
  xcode-select --install 2>/dev/null
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi
python3 install.py "$@"
echo
read -n 1 -s -r -p "Press any key to close... "
