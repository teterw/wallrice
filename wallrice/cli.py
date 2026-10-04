"""wallrice: the whole desktop takes its colours from the wallpaper.

  wallrice apply IMAGE [--effect FX]  set the wallpaper (animated) and re-theme everything from it
  wallrice pick                       full-screen picker with a live preview of the theme (Super+W)
  wallrice random                     a random wallpaper from the current mode (Shift+Super+W)
  wallrice next                       timer tick: a random wallpaper, unless paused
  wallrice mode [all|calm]            every collection, or only calm ones (photos, space)
  wallrice rotate off|MINUTES         change the wallpaper on a timer (default 30)
  wallrice pause | resume             no rotation and no animations while the machine is busy
  wallrice animations on|off          animated wallpaper changes
  wallrice bar [STYLE|mono|colour]    top bar style, with a live preview (GNOME); dock icon colours
  wallrice walls update [--background]  download or update the wallpaper collections
  wallrice walls review               keep or remove each picture; removed ones stay gone
  wallrice walls status               what's downloaded, kept and removed
  wallrice status                     current wallpaper and settings
  wallrice doctor                     what was detected, which pieces are active, what's missing

  FX: grow, wipe, wave, fade, random or none"""
import argparse
import json
import sys
from pathlib import Path

from . import __version__, collections, doctor, engine, setup
from .state import load_state, update_state

EFFECTS = (*engine.EFFECTS, "random", "none")


def die(msg, code=1):
    print(f"wallrice: {msg}", file=sys.stderr)
    return code


def apply(img, effect="random"):
    try:
        engine.apply(img, effect=effect)
    except engine.ApplyError as e:
        return die(str(e))
    return 0


def cmd_random(_args, avoid=True):
    st = load_state()
    img = collections.pick_random(st.get("mode", "all"), avoid=st.get("wallpaper") if avoid else None)
    if img is None:
        return die("no wallpapers yet: run  wallrice walls update")
    return apply(img)


def cmd_next(_args):
    """Timer tick: only downloaded collections rotate, never the distro's default wallpapers."""
    st = load_state()
    if st.get("paused"):
        return 0
    pics = [p for p in collections.wallpapers(st.get("mode", "all")) if collections.in_walls(p)]
    if st.get("wallpaper") and len(pics) > 1:
        pics = [p for p in pics if str(p) != st["wallpaper"]]
    if not pics:
        return 0
    import random
    return apply(random.choice(pics))


def cmd_pick(_args):
    try:
        from .ui import picker
    except (ImportError, ValueError) as e:  # no GTK: a rofi/wofi/fuzzel grid, or fzf in a terminal
        from .ui import fallback
        print(f"wallrice: the picker needs GTK 3 ({e}); using the fallback", file=sys.stderr)
        return fallback.pick()
    return picker.main()


def cmd_walls(args):
    if args.what == "update":
        if args.background:
            log = collections.update_in_background()
            print(f"Downloading in the background. Progress: tail -f {log}")
            return 0
        collections.update()
        return 0
    if args.what == "review":
        try:
            from .ui import review
        except (ImportError, ValueError) as e:
            return die(f"the review needs GTK 3 and cairo ({e}); see  wallrice doctor")
        return review.main()
    collections.status()
    return 0


def cmd_mode(args):
    if not args.mode:
        print(load_state().get("mode", "all"))
        return 0
    if args.mode not in collections.sets():
        return die(f"unknown mode {args.mode}: {', '.join(collections.sets())}")
    update_state(mode=args.mode)
    print(f"mode: {args.mode}")
    cur = load_state().get("wallpaper")
    if cur and Path(cur) not in collections.wallpapers(args.mode):
        return cmd_random(args)
    return 0


def cmd_rotate(args):
    minutes = 0 if args.minutes in ("off", "0") else None
    if minutes is None:
        try:
            minutes = int(args.minutes.rstrip("m"))
        except ValueError:
            return die("rotate off|MINUTES")
    update_state(rotate_minutes=minutes)
    setup.set_rotation(minutes if not load_state().get("paused") else 0)
    return 0


def cmd_pause(args):
    st = load_state()
    paused = args.cmd == "pause"
    if paused == bool(st.get("paused")):
        print("already " + ("paused" if paused else "running"))
        return 0
    update_state(paused=paused)
    setup.set_rotation(0 if paused else st.get("rotate_minutes", 30), say=lambda *a: None)
    print("paused: no rotation, no animations" if paused else "resumed")
    return 0


def set_bar(name):
    """`wallrice bar STYLE|mono|colour`: set it without the chooser (no GTK needed)."""
    from . import barstyles
    from .backends import gnome
    if name in ("mono", "colour", "color"):
        st = update_state(dock_mono=name == "mono")
    else:
        style = barstyles.get(name)
        if style.id != name and not (name.isdigit() and 1 <= int(name) <= len(barstyles.STYLES)):
            return die(f"unknown style {name}. Styles: " + ", ".join(
                f"{i + 1} {s.id}" for i, s in enumerate(barstyles.STYLES)), 2)
        st = update_state(bar_style=style.id)
    gnome.refresh_shell(st)
    print(f"top bar: {barstyles.get(st['bar_style']).name} · dock icons {'monochrome' if st['dock_mono'] else 'colour'}")
    return 0


def cmd_bar(args):
    if args.style:
        return set_bar(args.style)
    try:
        from .ui import barchooser
    except (ImportError, ValueError) as e:
        return die(f"the chooser needs GTK 3 ({e}); use  wallrice bar STYLE")
    return barchooser.main()


def cmd_animations(args):
    update_state(animations=args.onoff == "on")
    print(f"animations {args.onoff}")
    return 0


def cmd_status(_args):
    print(json.dumps(load_state(), indent=1, sort_keys=True))
    return 0


def cmd_login(_args):
    """Session start. A pause only lasts for one session; the theme is already in the desktop's own
    settings, so only per-session pieces are restarted here."""
    st = load_state()
    if st.get("paused"):
        update_state(paused=False)
        setup.set_rotation(st.get("rotate_minutes", 30), say=lambda *a: None)
    if not setup.has_systemd() and st.get("rotate_minutes"):
        import time
        while True:  # rotation without systemd
            time.sleep(st["rotate_minutes"] * 60)
            if not load_state().get("paused"):
                cmd_random(None)
    return 0


def parser():
    p = argparse.ArgumentParser(prog="wallrice", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"wallrice {__version__}")
    sub = p.add_subparsers(dest="cmd")
    a = sub.add_parser("apply", help="apply a wallpaper")
    a.add_argument("image")
    a.add_argument("--effect", choices=EFFECTS, default="random")
    sub.add_parser("pick", help="the picker")
    sub.add_parser("random", help="a random wallpaper")
    sub.add_parser("next", help="timer tick")
    m = sub.add_parser("mode", help="all or calm")
    m.add_argument("mode", nargs="?")
    r = sub.add_parser("rotate", help="rotation interval")
    r.add_argument("minutes")
    sub.add_parser("pause")
    sub.add_parser("resume")
    b = sub.add_parser("bar", help="top bar style")
    b.add_argument("style", nargs="?")
    an = sub.add_parser("animations")
    an.add_argument("onoff", choices=("on", "off"))
    w = sub.add_parser("walls", help="wallpaper collections")
    w.add_argument("what", choices=("update", "review", "status"))
    w.add_argument("--background", action="store_true", help="update: download detached, with a log")
    sub.add_parser("status")
    sub.add_parser("doctor")
    sub.add_parser("login", help=argparse.SUPPRESS)
    sub.add_parser("thumbs", help=argparse.SUPPRESS)
    for name in ("setup", "teardown"):
        s = sub.add_parser(name, help=argparse.SUPPRESS)
        s.add_argument("--dry-run", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    cmd = args.cmd
    if cmd is None:
        parser().print_help()
        return 2
    if cmd == "apply":
        return apply(args.image, args.effect)
    if cmd == "thumbs":
        n = collections.build_thumbs(collections.wallpapers(load_state().get("mode", "all")), say=print)
        print(f"{n} new thumbnails")
        return 0
    if cmd == "doctor":
        return doctor.report()
    if cmd == "setup":
        setup.install(dry_run=args.dry_run)
        return 0
    if cmd == "teardown":
        setup.uninstall(dry_run=args.dry_run)
        return 0
    handlers = {"pick": cmd_pick, "random": cmd_random, "next": cmd_next, "walls": cmd_walls, "mode": cmd_mode,
                "rotate": cmd_rotate, "pause": cmd_pause, "resume": cmd_pause, "animations": cmd_animations,
                "status": cmd_status, "login": cmd_login, "bar": cmd_bar}
    return handlers[cmd](args)
