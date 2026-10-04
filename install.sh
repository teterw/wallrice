#!/usr/bin/env bash
# wallrice installer. Per user: the program goes to ~/.local/share/wallrice and ~/.local/bin/wallrice,
# nothing needs root at run time. Only missing distro packages need sudo, and sudo asks for your
# password itself (it's never stored or passed on the command line).
#
#   ./install.sh             install or upgrade
#   ./install.sh --dry-run   show what would happen, change nothing
#   ./install.sh --yes       install missing packages without asking
#   ./install.sh --no-packages   never run the package manager
set -euo pipefail

DRY=0 YES=0 PKGS=1
for a in "$@"; do
    case "$a" in
        --dry-run|-n) DRY=1 ;;
        --yes|-y) YES=1 ;;
        --no-packages) PKGS=0 ;;
        -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "install.sh: unknown option $a" >&2; exit 2 ;;
    esac
done

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DATA=${XDG_DATA_HOME:-$HOME/.local/share}
DEST=$DATA/wallrice
BIN=$HOME/.local/bin

say() { printf '%s\n' "$*"; }
do_() { if [ "$DRY" = 1 ]; then say "  would run: $*"; else "$@"; fi; }

# ---------------------------------------------------------------- what is this machine?
ID="" ID_LIKE=""
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
fi
PM=""
for d in $ID $ID_LIKE; do
    case "$d" in
        fedora|rhel|centos) PM=dnf ;;
        debian|ubuntu) PM=apt ;;
        arch) PM=pacman ;;
        opensuse*|suse) PM=zypper ;;
    esac
    [ -n "$PM" ] && break
done
DESKTOP=$(printf '%s' "${XDG_CURRENT_DESKTOP:-}" | tr '[:upper:]' '[:lower:]')
say "wallrice installer: ${PRETTY_NAME:-unknown distro} · desktop ${DESKTOP:-?} · session ${XDG_SESSION_TYPE:-?}"

# ---------------------------------------------------------------- dependencies
command -v python3 >/dev/null || { say "wallrice needs python3 (3.9 or newer)."; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { say "wallrice needs Python 3.9 or newer."; exit 1; }

want=()   # logical names of what's missing
python3 -c 'import PIL' 2>/dev/null || want+=(pillow)
python3 -c 'import gi; gi.require_version("Gtk", "3.0"); from gi.repository import Gtk' 2>/dev/null || want+=(pygobject)
python3 -c 'import cairo' 2>/dev/null || want+=(cairo)
command -v git >/dev/null || want+=(git)
have_icons() { for d in "$DATA/icons" /usr/local/share/icons /usr/share/icons "$HOME/.icons"; do [ -d "$d/$1" ] && return 0; done; return 1; }
have_theme() { for d in "$DATA/themes" /usr/local/share/themes /usr/share/themes "$HOME/.themes"; do [ -d "$d/$1" ] && return 0; done; return 1; }
have_icons Papirus || want+=(papirus)
case "$DESKTOP" in *gnome*|*budgie*|*xfce*|*cinnamon*|*mate*|*hyprland*|*sway*) have_theme adw-gtk3-dark || want+=(adw-gtk3) ;; esac

pkgnames() {  # logical name -> this distro's package names
    case "$PM:$1" in
        dnf:pillow) echo python3-pillow ;; apt:pillow) echo python3-pil ;; pacman:pillow) echo python-pillow ;; zypper:pillow) echo python3-Pillow ;;
        dnf:pygobject) echo python3-gobject ;; apt:pygobject) echo python3-gi python3-gi-cairo gir1.2-gtk-3.0 ;;
        pacman:pygobject) echo python-gobject gtk3 ;; zypper:pygobject) echo python3-gobject python3-gobject-cairo typelib-1_0-Gtk-3_0 ;;
        dnf:cairo|zypper:cairo|apt:cairo) echo python3-cairo ;; pacman:cairo) echo python-cairo ;;
        *:git) echo git ;;
        *:papirus) echo papirus-icon-theme ;;
        dnf:adw-gtk3) echo adw-gtk3-theme ;; pacman:adw-gtk3) echo adw-gtk-theme ;; zypper:adw-gtk3) echo adw-gtk3 ;;
    esac
}
exists() {  # is this package name known to the package manager?
    case "$PM" in
        dnf) dnf -q info "$1" >/dev/null 2>&1 ;;
        apt) apt-cache show "$1" >/dev/null 2>&1 ;;
        pacman) pacman -Si "$1" >/dev/null 2>&1 ;;
        zypper) zypper -q info "$1" 2>/dev/null | grep -q "^Name" ;;
        *) return 1 ;;
    esac
}

if [ "${#want[@]}" -gt 0 ]; then
    pkgs=() unknown=()
    for w in "${want[@]}"; do
        names=$(pkgnames "$w")
        if [ -z "$names" ]; then unknown+=("$w"); continue; fi
        for n in $names; do
            # --no-packages: don't even ask the package manager (dnf refreshes its metadata to answer)
            if [ "$PKGS" = 0 ] || exists "$n"; then pkgs+=("$n"); else unknown+=("$w ($n)"); fi
        done
    done
    [ "${#unknown[@]}" -gt 0 ] && say "Not packaged here (wallrice works without them, with less): ${unknown[*]}"
    if [ "${#pkgs[@]}" -gt 0 ]; then
        case "$PM" in
            dnf) cmd=(sudo dnf install -y "${pkgs[@]}") ;;
            apt) cmd=(sudo apt-get install -y "${pkgs[@]}") ;;
            pacman) cmd=(sudo pacman -S --needed --noconfirm "${pkgs[@]}") ;;
            zypper) cmd=(sudo zypper install -y "${pkgs[@]}") ;;
        esac
        say "Missing packages: ${pkgs[*]}"
        if [ "$PKGS" = 0 ] || [ "$DRY" = 1 ]; then
            say "  install them with: ${cmd[*]}"
        else
            answer=n
            if [ "$YES" = 1 ]; then answer=y; elif [ -t 0 ]; then read -r -p "Install them now? sudo will ask for your password [y/N] " answer; fi
            case "$answer" in
                y|Y|yes) "${cmd[@]}" || say "Package install failed; wallrice will run with what's there." ;;
                *) say "  skipped. Later: ${cmd[*]}" ;;
            esac
        fi
    fi
fi

# ---------------------------------------------------------------- the program
say "Installing to $DEST"
do_ mkdir -p "$DEST" "$BIN"
for part in wallrice data bin gnome-extension; do
    [ -e "$SRC/$part" ] || continue
    do_ rm -rf "${DEST:?}/$part"
    do_ cp -r "$SRC/$part" "$DEST/$part"
done
do_ cp "$SRC/LICENSE" "$SRC/README.md" "$DEST/" 2>/dev/null || true
if [ "$DRY" = 0 ]; then
    find "$DEST" -name '__pycache__' -type d -prune -exec rm -rf {} +
    chmod +x "$DEST/bin/wallrice"
fi
do_ ln -sf "$DEST/bin/wallrice" "$BIN/wallrice"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) say "Note: $BIN isn't on your PATH. Add it (e.g. in ~/.bashrc):  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

# ---------------------------------------------------------------- per-user setup (menu, keys, timer, first theme)
if [ "$DRY" = 1 ]; then
    python3 "$SRC/bin/wallrice" setup --dry-run
else
    "$BIN/wallrice" setup
fi

say ""
say "Done. Super+W picks a wallpaper; 'wallrice doctor' shows what's active."
if [ "$DRY" = 0 ] && [ -t 0 ] && [ ! -d "$(xdg-user-dir PICTURES 2>/dev/null || echo "$HOME/Pictures")/walls/space" ]; then
    read -r -p "Download the wallpaper collections now (about 1.4 GB, in the background)? [y/N] " answer
    case "$answer" in y|Y|yes) "$BIN/wallrice" walls update --background ;; *) say "Later: wallrice walls update" ;; esac
fi
