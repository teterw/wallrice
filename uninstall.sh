#!/usr/bin/env bash
# wallrice uninstaller: puts back every setting and file wallrice changed (from the backup it made
# before the first change), removes its shortcuts, timer, menu entries, themes and the program.
# Your wallpapers and review choices are kept unless you type "yes" when asked.
#
#   ./uninstall.sh            uninstall
#   ./uninstall.sh --dry-run  show what would happen, change nothing
set -euo pipefail

DRY=0
for a in "$@"; do
    case "$a" in
        --dry-run|-n) DRY=1 ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "uninstall.sh: unknown option $a" >&2; exit 2 ;;
    esac
done

DATA=${XDG_DATA_HOME:-$HOME/.local/share}
DEST=$DATA/wallrice
BIN=$HOME/.local/bin
CONF=${XDG_CONFIG_HOME:-$HOME/.config}/wallrice
CACHE=${XDG_CACHE_HOME:-$HOME/.cache}/wallrice
SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

say() { printf '%s\n' "$*"; }
do_() { if [ "$DRY" = 1 ]; then say "  would run: $*"; else "$@"; fi; }

if [ -x "$DEST/bin/wallrice" ]; then
    RUN=("$DEST/bin/wallrice")
else
    RUN=(python3 "$SRC/bin/wallrice")
fi
if [ "$DRY" = 1 ]; then "${RUN[@]}" teardown --dry-run; else "${RUN[@]}" teardown; fi

# Stop a running picker, review or download. Anchored to a python process running wallrice: a looser
# pattern would also match any shell whose command line merely mentions "wallrice pick".
if [ "$DRY" = 0 ]; then
    pkill -f -- '^[^ ]*python[0-9.]* ([^ ]*/bin/wallrice|-m wallrice) (pick|walls)' 2>/dev/null || true
fi
do_ rm -f "$BIN/wallrice"
do_ rm -rf "$CACHE"
# keep the backup until everything else is gone, then the program
do_ rm -rf "$DEST"

WALLS="$(xdg-user-dir PICTURES 2>/dev/null || echo "$HOME/Pictures")/walls"
if [ "$DRY" = 0 ] && [ -t 0 ] && [ -d "$WALLS" ]; then
    say "Your wallpapers ($WALLS, $(du -sh --exclude=.git "$WALLS" 2>/dev/null | cut -f1)) and review choices are kept."
    read -r -p "Delete them too? This can't be undone. Type yes to delete: " answer
    if [ "$answer" = "yes" ]; then
        rm -rf "$WALLS" "$CONF"
        say "Deleted."
    fi
fi
say "wallrice is uninstalled."
