#!/usr/bin/env bash
# Inside a test container: start DESKTOP headless, apply wallpapers with wallrice, and save screenshots
# of the themed desktop, a terminal, the transitions, the picker and the review to /out.
#   bash /src/tools/desktops/run.sh xfce|sway|kde     (tools/desktop-test.sh runs it)
set -uo pipefail
DESKTOP=${1:?xfce, sway or kde}
export HOME=/root XDG_RUNTIME_DIR=/tmp/run WALLRICE_WALLS=/walls WALLRICE_TERMINALS=0
W=(python3 /src/bin/wallrice)
log() { printf '[%s] %s\n' "$DESKTOP" "$*"; }

if [ "${2:-}" != inner ]; then  # outside the session bus: the display server, then run again inside
    mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
    case "$DESKTOP" in
        xfce)
            Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/out/xvfb.log 2>&1 &
            export DISPLAY=:99 XDG_CURRENT_DESKTOP=XFCE XDG_SESSION_TYPE=x11 ;;
        sway)
            export XDG_CURRENT_DESKTOP=sway XDG_SESSION_TYPE=wayland WLR_BACKENDS=headless WLR_RENDERER=pixman \
                   WLR_LIBINPUT_NO_DEVICES=1 WLR_HEADLESS_OUTPUTS=1 ;;
        kde)
            export XDG_CURRENT_DESKTOP=KDE XDG_SESSION_TYPE=wayland KDE_FULL_SESSION=true QT_QPA_PLATFORM=wayland ;;
    esac
    sleep 1
    exec dbus-run-session -- bash "$0" "$DESKTOP" inner
fi

state() {  # state LABEL: what the desktop has now (KDE can't take screenshots in a GPU-less container)
    [ "$DESKTOP" = kde ] || return 0
    {
        echo "== $1"
        echo "ColorScheme=$(kreadconfig6 --file kdeglobals --group General --key ColorScheme)"
        echo "Selection=$(kreadconfig6 --file kdeglobals --group Colors:Selection --key BackgroundNormal)"
        echo "IconTheme=$(kreadconfig6 --file kdeglobals --group Icons --key Theme)"
        grep -m1 '^Image=' ~/.config/plasma-org.kde.plasma.desktop-appletsrc 2>/dev/null
        echo "gtk-theme=$(dconf read /org/gnome/desktop/interface/gtk-theme)"
    } >> /out/state.txt
}

shot() {  # shot NAME
    case "$DESKTOP" in
        xfce) import -window root "/out/$1.png" ;;
        sway) grim "/out/$1.png" ;;
        kde)  timeout 20 python3 /src/tools/desktops/kde_shot.py "/out/$1.png" ;;
    esac
}

case "$DESKTOP" in
    xfce) xfce4-session >/out/session.log 2>&1 & ;;
    sway)
        mkdir -p ~/.config/sway && touch ~/.config/sway/wallrice
        printf 'output HEADLESS-1 resolution 1920x1080\nexec waybar\ninclude ~/.config/sway/wallrice\nfor_window [app_id="foot"] floating enable, resize set 1100 640, move position center\n' > /tmp/sway.conf
        sway -c /tmp/sway.conf >/out/session.log 2>&1 &
        sleep 3
        for f in "$XDG_RUNTIME_DIR"/wayland-*; do [[ $f == *.lock ]] || WAYLAND_DISPLAY=${f##*/}; done
        for f in "$XDG_RUNTIME_DIR"/sway-ipc.*; do SWAYSOCK=$f; done
        export WAYLAND_DISPLAY SWAYSOCK ;;
    kde)
        KWIN_SCREENSHOT_NO_PERMISSION_CHECKS=1 kwin_wayland --virtual --width 1920 --height 1080 --xwayland \
            --no-lockscreen plasmashell >/out/session.log 2>&1 &
        sleep 6
        export WAYLAND_DISPLAY=wayland-0 ;;
esac
sleep 6
mapfile -t PICS < <(find /walls/space -name '*.jpg' | sort | head -4)
log "apply ${PICS[0]##*/}"
"${W[@]}" apply "${PICS[0]}" --effect none
"${W[@]}" doctor > /out/doctor.txt 2>&1
state "after ${PICS[0]##*/}"
TERMCMD='ls --color=always /usr; printf "\n\e[31m red \e[32m green \e[33m yellow \e[34m blue \e[35m magenta \e[36m cyan\e[0m\n"; sleep 600'
case "$DESKTOP" in
    xfce) xfce4-terminal --geometry=100x28+300+200 -x bash -c "$TERMCMD" & ;;
    sway) foot bash -c "$TERMCMD" & ;;
    kde)  konsole -e bash -c "$TERMCMD" & ;;
esac
sleep 4
shot desktop
log "transitions"
for i in 1 2; do
    fx=$([ "$i" = 1 ] && echo grow || echo wipe)
    "${W[@]}" apply "${PICS[$i]}" --effect "$fx" & APPLY=$!
    for k in 0 1 2 3 4 5 6 7; do shot "fx-$fx-$k"; sleep 0.1; done
    wait "$APPLY"
    state "after ${PICS[$i]##*/} ($fx)"
done
sleep 2
shot desktop-2
log "picker"
"${W[@]}" pick & PICK=$!
sleep 6; shot picker
if kill -0 "$PICK" 2>/dev/null; then log "picker running"; else log "picker NOT running"; fi
kill "$PICK" 2>/dev/null
log "review"
XDG_CONFIG_HOME=/tmp/review-cfg "${W[@]}" walls review & REV=$!
sleep 6; shot review
if kill -0 "$REV" 2>/dev/null; then log "review running"; else log "review NOT running"; fi
kill "$REV" 2>/dev/null
log "done"
