"""Pieces several desktop backends share: the X11 transition overlay, GTK settings files, xsettingsd,
and GTK settings over dconf (what GTK apps on Wayland read)."""
import configparser
import io
import select
import subprocess
import sys
from pathlib import Path

from .. import paths
from ..render import gtk, icons
from ..sh import run
from .base import gv_str


class X11Overlay:
    """The animated change on X11 (wallrice.ui.transition_x11): a desktop-layer window that covers the
    wallpaper, so the switch underneath stays hidden while it animates."""

    def __init__(self):
        self.procs = []

    def start(self, old, new, effect, env):
        if effect == "none" or env.session != "x11" or not old or not Path(old).is_file() or Path(old) == Path(new):
            return False
        try:
            p = subprocess.Popen([sys.executable, "-m", "wallrice.ui.transition_x11", str(old), str(new), effect],
                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, cwd=str(paths.SRC))
        except OSError:
            return False
        ready, _, _ = select.select([p.stdout], [], [], 4.0)
        if not ready or p.stdout.readline().strip() != "ready":
            p.kill()  # never leave a stuck animation over the desktop
            return False
        self.procs.append(p)
        return True

    def finish(self):
        """Wait for running animations: a timer job's processes end with the job."""
        for p in self.procs:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                p.kill()
        self.procs = []


def ini_update(path, section, values):
    """The text of an ini file with these keys set (others kept), for GTK's settings.ini."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        text = ""
    return ini_set(text, section, values)


def ini_set(text, section, values):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        cp.read_string(text)
    except configparser.Error:
        cp = configparser.ConfigParser(interpolation=None)
        cp.optionxform = str
    if not cp.has_section(section):
        cp.add_section(section)
    for k, v in values.items():
        cp.set(section, k, str(v))
    out = io.StringIO()
    cp.write(out, space_around_delimiters=False)
    return out.getvalue()


def gtk_settings_files(ctx):
    """~/.config/gtk-{3,4}.0/settings.ini: the theme for GTK apps started from now on (on desktops
    without a settings daemon, that's how GTK finds its theme)."""
    values = {}
    if ctx.on("apps"):
        values.update({"gtk-theme-name": gtk.theme_name(ctx.slot), "gtk-application-prefer-dark-theme": "1"})
    if ctx.icons:
        values["gtk-icon-theme-name"] = icons.theme_name(ctx.slot)
    out = {}
    for ver in ("gtk-3.0", "gtk-4.0"):
        path = paths.config_home() / ver / "settings.ini"
        v = dict(values)
        if ver == "gtk-4.0":
            v.pop("gtk-theme-name", None)  # libadwaita apps warn about a theme name; they use gtk.css
        if v:
            out[path] = ini_update(path, "Settings", v)
    return out


def xsettingsd(ctx, run=run):
    """Desktops whose GTK settings come from xsettingsd (i3, bspwm, KDE's X11 GTK bridge): update its
    config and make it reload, so running GTK apps switch theme at once."""
    conf = paths.config_home() / "xsettingsd" / "xsettingsd.conf"
    rc, _ = run("pgrep", "-x", "xsettingsd")
    if rc != 0 or not (ctx.on("apps") or ctx.icons):
        return False
    lines = [l for l in (conf.read_text().splitlines() if conf.is_file() else [])
             if not l.startswith(("Net/ThemeName", "Net/IconThemeName"))]
    if ctx.on("apps"):
        lines.append(f'Net/ThemeName "{gtk.theme_name(ctx.slot)}"')
    if ctx.icons:
        lines.append(f'Net/IconThemeName "{icons.theme_name(ctx.slot)}"')
    conf.parent.mkdir(parents=True, exist_ok=True)
    conf.write_text("\n".join(lines) + "\n")
    run("pkill", "-HUP", "-x", "xsettingsd")
    return True


def dconf_interface_keys(ctx):
    """GTK apps on Wayland (and GNOME-based settings daemons) read org.gnome.desktop.interface."""
    keys = {}
    if ctx.on("apps"):
        keys.update({"/org/gnome/desktop/interface/gtk-theme": gv_str(gtk.theme_name(ctx.slot)),
                     "/org/gnome/desktop/interface/color-scheme": gv_str("prefer-dark")})
    if ctx.icons:
        keys["/org/gnome/desktop/interface/icon-theme"] = gv_str(icons.theme_name(ctx.slot))
    return keys


def first_tool(env, *names):
    """The first of these programs the environment has."""
    return next((n for n in names if env.has(n)), None)
