#!/usr/bin/env bash
# Run the wallrice GNOME Shell extension in a private, headless GNOME Shell (its own home folder,
# dconf, runtime dir and session bus: the real desktop is never touched), drive wallrice against it,
# and save screenshots of the top bar styles and the wallpaper transitions.
#
#   tools/shell-test.sh OUTDIR [WALLS_DIR]
#
# Needs gnome-shell 45+ (--headless), dbus-run-session, dconf, python3 with Pillow.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
OUT=$(mkdir -p "${1:?usage: tools/shell-test.sh OUTDIR [WALLS_DIR]}" && cd "$1" && pwd)
WALLS=${2:-$(xdg-user-dir PICTURES 2>/dev/null || echo "$HOME/Pictures")/walls}
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

export HOME=$T/home
export XDG_CONFIG_HOME=$HOME/.config XDG_DATA_HOME=$HOME/.local/share XDG_CACHE_HOME=$HOME/.cache
export XDG_RUNTIME_DIR=$T/run XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_TYPE=wayland
export WALLRICE_WALLS=$WALLS WALLRICE_TERMINALS=0
unset WAYLAND_DISPLAY DISPLAY DBUS_SESSION_BUS_ADDRESS
mkdir -p "$XDG_RUNTIME_DIR" "$XDG_DATA_HOME/gnome-shell/extensions" "$XDG_CONFIG_HOME"
chmod 700 "$XDG_RUNTIME_DIR"
cp -r "$REPO/gnome-extension/wallrice@teterw.github.io" "$XDG_DATA_HOME/gnome-shell/extensions/"

exec dbus-run-session -- python3 "$REPO/tools/shell_session.py" "$REPO" "$OUT"
