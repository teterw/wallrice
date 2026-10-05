"""GNOME (also Budgie and Ubuntu's GNOME): everything through dconf, in one transaction per step.

  wallpaper      org.gnome.desktop.background picture-uri (+ -dark), picture-options zoom
  GTK3 apps      gtk-theme Wallrice-a|b (live: a theme-name change makes them re-read it)
  GTK4 apps      ~/.config/gtk-4.0/gtk.css (read at app start) + accent-color, live
  Shell accent   accent-color: a named colour only (GNOME 47+), the nearest to the wallpaper's accent
  icons          icon-theme Wallrice-Papirus-a|b (folders in the accent's Papirus colour)
  terminal       Ptyxis palette wallrice-a|b on every profile; escape sequences for open windows
  dock           Dash to Dock / Ubuntu Dock background and running-dot colours
  transitions    GNOME cross-fades by itself; the wallrice Shell extension adds grow/wipe/wave
  Super+W        a custom keybinding in org.gnome.settings-daemon.plugins.media-keys
"""
import json
from pathlib import Path

from .. import barstyles, paths
from ..color import rgb2hex
from ..render import gtk, icons
from ..state import load_state
from ..theme import nearest
from .base import Backend, gv_list, gv_str, gv_strip

# libadwaita's accent colours (GNOME 47+)
ACCENTS = {"blue": "#3584e4", "teal": "#2190a4", "green": "#3a944a", "yellow": "#c88800", "orange": "#ed5b00",
           "red": "#e62d42", "pink": "#d56199", "purple": "#9141ac", "slate": "#6f8396"}

IFACE = "/org/gnome/desktop/interface"
BG = "/org/gnome/desktop/background"
DOCK = "/org/gnome/shell/extensions/dash-to-dock"
KEYS = "/org/gnome/settings-daemon/plugins/media-keys"
PTYXIS = "/org/gnome/Ptyxis"
DOCK_UUIDS = ("dash-to-dock@micxgx.gmail.com", "ubuntu-dock@ubuntu.com")
EXT_UUID = "wallrice@teterw.github.io"
EXT_PATH = "/io/github/teterw/Wallrice"
EXT_IFACE = "io.github.teterw.Wallrice"
GNOME_FADE = 1.0  # GNOME Shell's own background cross-fade (FADE_ANIMATION_TIME)


class Gnome(Backend):
    name = "gnome"
    features = {"wallpaper": "gsettings", "live colours": "A/B GTK theme, accent-color, icons, Ptyxis, dock",
                "transition": "Shell cross-fade, or the wallrice extension", "Super+W": "custom keybinding"}

    # ---------------------------------------------------------------- dconf helpers

    # ---------------------------------------------------------------- state

    def current_slot(self):
        name = gv_strip(self.read(f"{IFACE}/gtk-theme"))
        if name in (gtk.theme_name("a"), gtk.theme_name("b")):
            return name[-1]
        return None

    def current_wallpaper(self):
        uri = gv_strip(self.read(f"{BG}/picture-uri-dark")) or gv_strip(self.read(f"{BG}/picture-uri"))
        if uri and uri.startswith("file://"):
            from urllib.parse import unquote, urlparse
            return Path(unquote(urlparse(uri).path))
        return None

    def ptyxis_profiles(self):
        if not self.env.has("ptyxis"):
            return []
        return gv_list(self.read(f"{PTYXIS}/profile-uuids"))

    def dock_installed(self):
        dirs = [paths.data_home() / "gnome-shell" / "extensions"] + [Path(d) / "gnome-shell" / "extensions"
                                                                      for d in ("/usr/local/share", "/usr/share")]
        return any((d / u).is_dir() for d in dirs for u in DOCK_UUIDS)

    def extension(self, method, *args):
        """Call the wallrice Shell extension over D-Bus; None when it isn't running."""
        if not self.env.has("gdbus"):
            return None
        rc, out = self.run("gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", EXT_PATH,
                           "--method", f"{EXT_IFACE}.{method}", *(gv_str(a) for a in args), timeout=3)
        return out.strip() if rc == 0 else None

    # ---------------------------------------------------------------- applying

    def outputs(self, ctx):
        """The stylesheet and settings the wallrice Shell extension loads (and reloads live)."""
        return shell_files(ctx.theme)

    def theme_keys(self, ctx):
        th = ctx.theme
        keys = {f"{IFACE}/color-scheme": gv_str("prefer-dark"),
                f"{IFACE}/gtk-theme": gv_str(gtk.theme_name(ctx.slot)),
                f"{IFACE}/accent-color": gv_str(nearest(th["accent"], ACCENTS))}
        if ctx.icons:
            keys[f"{IFACE}/icon-theme"] = gv_str(icons.theme_name(ctx.slot))
        if self.dock_installed():
            acc = rgb2hex(th["accent"])
            keys.update({f"{DOCK}/custom-background-color": "true",
                         f"{DOCK}/background-color": gv_str(rgb2hex(th["bg"])),
                         f"{DOCK}/custom-theme-customize-running-dots": "true",
                         f"{DOCK}/custom-theme-running-dots-color": gv_str(acc),
                         f"{DOCK}/custom-theme-running-dots-border-color": gv_str(acc)})
        return keys

    def ptyxis_keys(self, ctx):
        """Every Ptyxis profile on the fresh wallrice palette (none when terminal colours are off)."""
        if not ctx.terminals:
            return {}
        return {f"{PTYXIS}/Profiles/{uuid}/palette": gv_str(f"wallrice-{ctx.term_slot}")
                for uuid in self.ptyxis_profiles()}

    def current_term_slot(self):
        for uuid in self.ptyxis_profiles():
            name = gv_strip(self.read(f"{PTYXIS}/Profiles/{uuid}/palette"))
            if name in ("wallrice-a", "wallrice-b"):
                return name[-1]
        return None

    def is_terminal_setting(self, key):
        return key.startswith(f"{PTYXIS}/")

    def terminal_steps(self, ctx):
        keys = self.ptyxis_keys(ctx)
        return [("Ptyxis palette", lambda: self.load(keys))] if keys else []

    def wallpaper_keys(self, img):
        uri = gv_str(Path(img).as_uri())
        return {f"{BG}/picture-uri": uri, f"{BG}/picture-uri-dark": uri, f"{BG}/picture-options": gv_str("zoom")}

    def settings_touched(self, ctx):
        return sorted({**self.wallpaper_keys(ctx.img), **self.theme_keys(ctx), **self.ptyxis_keys(ctx)})

    def set_wallpaper(self, ctx):
        """With the wallrice extension running, it plays the effect (or none: the picker has already
        animated the change). Without it, GNOME cross-fades for a second by itself."""
        length = GNOME_FADE
        out = self.extension("Prepare", ctx.effect)  # "(1.3,)": the effect's length in seconds
        if out:
            try:
                length = float(out.strip("(),"))
            except ValueError:
                pass
        self.load(self.wallpaper_keys(ctx.img))
        ctx.settle = length
        return length * 0.5

    def activate(self, ctx):
        keys = {**self.theme_keys(ctx), **self.ptyxis_keys(ctx)}  # one transaction: everything at once
        return [("GNOME theme, accent, icons, terminal and dock", lambda: self.load(keys))]

    # ---------------------------------------------------------------- Super+W

    def bind_key(self, binding, command, name):
        path = f"{KEYS}/custom-keybindings/{name}/"
        current = gv_list(self.read(f"{KEYS}/custom-keybindings"))
        if path not in current:
            current.append(path)
        self.load({f"{KEYS}/custom-keybindings": "[" + ", ".join(gv_str(p) for p in current) + "]",
                   f"{path}name": gv_str(name), f"{path}command": gv_str(command), f"{path}binding": gv_str(binding)})
        return True

    def unbind_keys(self):
        current = gv_list(self.read(f"{KEYS}/custom-keybindings"))
        mine = [p for p in current if p.rstrip("/").rsplit("/", 1)[-1].startswith("wallrice")]
        if not mine:
            return False
        rest = [p for p in current if p not in mine]
        self.load({f"{KEYS}/custom-keybindings": "[" + ", ".join(gv_str(p) for p in rest) + "]" if rest else "@as []"})
        for p in mine:
            self.run("dconf", "reset", "-f", p)
        return True

    # ---------------------------------------------------------------- doctor

    def doctor(self):
        out = []
        ok = gtk.find_dir("themes", gtk.BASE) is not None
        pkgs = " ".join(self.env.packages("adw-gtk3"))
        out.append((ok, "adw-gtk3 theme " + ("found" if ok else "missing: GTK3 apps keep the plain Adwaita look"
                                             + (f"  (install: {pkgs})" if pkgs else ""))))
        out.append((self.env.has("dconf"), "dconf " + ("found" if self.env.has("dconf") else "missing: nothing can be set live")))
        st = self.extension("Version")
        out.append((True if st else None, f"wallrice Shell extension {'active ' + st if st else 'not active: GNOME cross-fades wallpapers itself'}"))
        out.append((True if self.dock_installed() else None,
                    "Dash to Dock " + ("found: its colours follow the wallpaper" if self.dock_installed() else "not installed (optional)")))
        if self.env.has("ptyxis"):
            from ..state import load_state
            on = load_state().get("terminal_colors", True)
            out.append((True, f"Ptyxis: {len(self.ptyxis_profiles())} profile(s) "
                              + ("get the wallpaper's palette" if on else "keep their own palette (terminal colours off)")))
        return out


def gnome_extensions_dir():
    return paths.data_home() / "gnome-shell" / "extensions"


def shell_css_path():
    return paths.data() / "gnome-shell.css"


def shell_files(theme, st=None):
    """{path: text} for the extension: its stylesheet, and its settings (bar style, dock icons)."""
    st = st or load_state()
    style = barstyles.get(st.get("bar_style"))
    settings = {"bar_style": style.id, "dock_mono": bool(st.get("dock_mono", True)), "workspaces": 4}
    return {shell_css_path(): barstyles.shell_css(theme, style, dock=True),
            paths.data() / "gnome-shell.json": json.dumps(settings, indent=1) + "\n"}


def refresh_shell(st=None):
    """Rewrite the extension's files from the current wallpaper (after a bar or dock setting changed):
    the extension notices and restyles the real top bar at once."""
    from ..palette import extract
    from ..state import write_atomic
    from ..theme import derive
    st = st or load_state()
    cur = st.get("wallpaper")
    if not cur or not Path(cur).is_file():
        return False
    for path, text in shell_files(derive(extract(cur)), st).items():
        write_atomic(path, text)
    return True

