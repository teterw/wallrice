"""One-time per-user setup and its undo (install.sh and uninstall.sh call these): app menu entries,
autostart, the rotation timer, Super+W. No root needed."""
import shutil
from pathlib import Path

from . import backends, backup, paths
from .detect import detect
from .sh import run
from .state import load_state, write_atomic

ENTRIES = (("wallrice-pick", "Wallpapers", "Pick a wallpaper; the desktop takes its colours", "pick",
            "preferences-desktop-wallpaper"),
           ("wallrice-review", "Review wallpapers", "Keep or remove each downloaded wallpaper", "walls review",
            "view-preview"),
           ("wallrice-bar", "Top bar style", "Choose how the top bar looks, with a live preview", "bar",
            "preferences-desktop-appearance"))
KEYS = (("<Super>w", "pick", "wallrice-pick"), ("<Shift><Super>w", "random", "wallrice-random"))
UNITS = ("wallrice-rotate.service", "wallrice-rotate.timer")


def exe():
    """The command to run wallrice: the installed launcher, else this checkout's bin/wallrice."""
    installed = paths.home() / ".local" / "bin" / "wallrice"
    return str(installed if installed.exists() else paths.SRC / "bin" / "wallrice")


def has_systemd():
    rc, out = run("systemctl", "--user", "is-system-running")
    return rc == 0 or out.strip() in ("degraded", "starting", "running")


def timer_text(minutes):
    return ("[Unit]\nDescription=wallrice: change the wallpaper on a timer\n\n[Timer]\n"
            f"OnActiveSec={minutes}min\nOnUnitActiveSec={minutes}min\n\n[Install]\nWantedBy=timers.target\n")


def service_text():
    # oneshot: the job waits for the transition to finish, so systemd doesn't kill the animation
    return ("[Unit]\nDescription=wallrice: next wallpaper\n\n[Service]\nType=oneshot\n"
            f"ExecStart={exe()} next\n")


def set_rotation(minutes, dry_run=False, say=print):
    """Rotate every `minutes` (0 = off): a systemd user timer, or the autostart loop without systemd."""
    units = paths.config_home() / "systemd" / "user"
    if not has_systemd():
        say("no systemd user session: rotation runs from the autostart loop (wallrice login)")
        return
    if minutes <= 0:
        say("rotation off")
        if not dry_run:
            run("systemctl", "--user", "disable", "--now", "wallrice-rotate.timer")
        return
    say(f"rotation every {minutes} min (systemd user timer)")
    if dry_run:
        return
    write_atomic(units / "wallrice-rotate.service", service_text())
    write_atomic(units / "wallrice-rotate.timer", timer_text(minutes))
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "wallrice-rotate.timer")
    run("systemctl", "--user", "restart", "wallrice-rotate.timer")


def install(dry_run=False, say=print):
    env = detect()
    be = backends.get(env)
    st = load_state()
    apps_dir = paths.data_home() / "applications"
    for name, title, comment, args, icon in ENTRIES:
        say(f"menu entry: {title}")
        if not dry_run:
            write_atomic(apps_dir / f"{name}.desktop",
                         f"[Desktop Entry]\nType=Application\nName={title}\nComment={comment}\n"
                         f"Exec={exe()} {args}\nIcon={icon}\nCategories=Settings;DesktopSettings;\nTerminal=false\n")
    say("autostart: wallrice login (session start)")
    if not dry_run:
        write_atomic(paths.config_home() / "autostart" / "wallrice.desktop",
                     "[Desktop Entry]\nType=Application\nName=wallrice\nComment=Wallpaper theme: session start\n"
                     f"Exec={exe()} login\nNoDisplay=true\nX-GNOME-Autostart-enabled=true\n")
    for binding, args, name in KEYS:
        if dry_run:
            say(f"shortcut {binding}: wallrice {args}")
            continue
        try:
            done = be.bind_key(binding, f"{exe()} {args}", name)
        except Exception as e:  # noqa: BLE001
            done, why = False, str(e)
        else:
            why = "this desktop's shortcuts aren't supported yet"
        say(f"shortcut {binding}: wallrice {args}" if done else
            f"shortcut {binding}: add it yourself in the desktop's keyboard settings: {exe()} {args}  ({why})")
    set_rotation(st.get("rotate_minutes", 30), dry_run, say)
    if env.has("update-desktop-database") and not dry_run:
        run("update-desktop-database", str(apps_dir))
    if be.name == "gnome" and env.has("gnome-shell"):
        install_extension(be, dry_run, say)
    first_theme(be, st, dry_run, say)
    return be


EXT_UUID = "wallrice@teterw.github.io"
ENABLED = "/org/gnome/shell/enabled-extensions"


def extension_dir():
    return paths.data_home() / "gnome-shell" / "extensions" / EXT_UUID


def install_extension(be, dry_run=False, say=print):
    """Copy the Shell extension into place and enable it. A running GNOME on Wayland only finds a new
    extension at the next login; an upgrade is picked up by re-enabling it."""
    from .backends.base import gv_list, gv_str
    src = paths.resource("gnome-extension", EXT_UUID)
    if not src.is_dir():
        say("GNOME Shell extension: not found in this copy of wallrice, skipped")
        return
    dest = extension_dir()
    say(f"GNOME Shell extension: {dest}")
    if dry_run:
        return
    was_there = dest.is_dir()
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(src, dest)
    enabled = gv_list(be.read(ENABLED))
    if EXT_UUID not in enabled:
        be.load({ENABLED: "[" + ", ".join(gv_str(u) for u in enabled + [EXT_UUID]) + "]"})
    if be.read("/org/gnome/shell/disable-user-extensions") == "true":
        say("  note: GNOME has user extensions switched off (Extensions app); the top bar and transitions need them")
    rc, _ = run("gnome-extensions", "info", EXT_UUID)
    if rc == 0:  # the Shell knows it already (an upgrade): reload it now
        run("gnome-extensions", "disable", EXT_UUID)
        run("gnome-extensions", "enable", EXT_UUID)
        say("  reloaded")
    else:
        say("  log out and back in once to start it (GNOME can't load a new extension into a running session)"
            if not was_there else "  enabled")


def uninstall_extension(be, dry_run=False, say=print):
    from .backends.base import gv_list, gv_str
    dest = extension_dir()
    if not dest.exists():
        return
    say(f"remove {dest}")
    if dry_run:
        return
    run("gnome-extensions", "disable", EXT_UUID)
    enabled = [u for u in gv_list(be.read(ENABLED)) if u != EXT_UUID]
    be.load({ENABLED: "[" + ", ".join(gv_str(u) for u in enabled) + "]" if enabled else "@as []"})
    shutil.rmtree(dest, ignore_errors=True)


def first_theme(be, st, dry_run=False, say=print):
    """Theme the desktop from the wallpaper it shows now, so it matches straight after installing."""
    from . import collections, engine
    if st.get("wallpaper") and Path(st["wallpaper"]).is_file():
        return
    img = be.current_wallpaper()
    if not img or not img.is_file() or img.suffix.lower() not in engine.IMAGE_EXT:
        img = collections.pick_random(st.get("mode", "all"))
    if not img:
        say("no wallpaper to start from yet: run  wallrice walls update")
        return
    say(f"first theme from {img}")
    if not dry_run:
        try:
            engine.apply(img, effect="none", backend=be)
        except engine.ApplyError as e:
            say(f"couldn't theme from {img.name}: {e}")


def uninstall(dry_run=False, say=print):
    env = detect()
    be = backends.get(env)
    if not dry_run:
        run("systemctl", "--user", "disable", "--now", "wallrice-rotate.timer")
    for unit in UNITS:
        p = paths.config_home() / "systemd" / "user" / unit
        if p.exists():
            say(f"remove {p}")
            if not dry_run:
                p.unlink()
    if not dry_run:
        run("systemctl", "--user", "daemon-reload")
    say("remove shortcuts")
    if not dry_run:
        be.unbind_keys()
    if be.name == "gnome":
        uninstall_extension(be, dry_run, say)
    for p in [paths.data_home() / "applications" / f"{n}.desktop" for n, *_ in ENTRIES] + \
             [paths.config_home() / "autostart" / "wallrice.desktop"]:
        if p.exists():
            say(f"remove {p}")
            if not dry_run:
                p.unlink()
    n = backup.restore(dry_run=dry_run, say=say)
    say(f"restored {n} setting(s) and file(s) from the backup")
    for base, prefix in ((paths.data_home() / "themes", "Wallrice-"), (paths.data_home() / "icons", "Wallrice-")):
        for d in sorted(base.glob(prefix + "*")) if base.is_dir() else []:
            say(f"remove {d}")
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
    for f in [*paths.data_home().glob("org.gnome.Ptyxis/palettes/wallrice-*.palette"),
              paths.data() / "gnome-shell.css", paths.data() / "gnome-shell.json",
              *(paths.config_home() / c for c in ("kitty/wallrice.conf", "alacritty/wallrice.toml", "foot/wallrice.ini",
                                                  "wezterm/colors/wallrice.toml", "btop/themes/wallrice.theme",
                                                  "rofi/wallrice-colors.rasi", "wofi/wallrice.css", "fuzzel/wallrice.ini",
                                                  "waybar/wallrice.css")),
              paths.data_home() / "konsole" / "Wallrice.colorscheme"]:
        if Path(f).exists():
            say(f"remove {f}")
            if not dry_run:
                Path(f).unlink()
    say(f"kept: your wallpapers ({paths.walls()}) and review choices ({paths.review_file()})")
