#!/usr/bin/env bash
# Removes g-script from your app menu. Add --purge to also delete pairing data and logs.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
. ./_term.sh
gs_in_terminal "$PWD/uninstall.sh" "$@"
python3 install.py --uninstall "$@"
