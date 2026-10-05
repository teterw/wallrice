"""Xfce (X11): everything through xfconf.

  wallpaper      xfce4-desktop /backdrop/screen0/monitor*/workspace*/last-image, image-style 5 (zoom)
  GTK apps       xsettings /Net/ThemeName Wallrice-a|b (live: xfsettingsd tells every GTK app)
  icons          xsettings /Net/IconThemeName Wallrice-Papirus-a|b
  panel          xfce4-panel and notifications styled from the GTK theme's CSS
  terminal       xfce4-terminal colours in xfconf; escape sequences for open windows
  transitions    the X11 overlay (grow / wipe / wave / fade behind the windows)
  Super+W        xfce4-keyboard-shortcuts /commands/custom/<Super>w
"""
from pathlib import Path

from ..color import rgb2hex
from ..render import gtk, icons
from ..theme import hexes
from .base import Backend
from .common import X11Overlay

OVERLAY_HALF = 0.7  # seconds into the overlay's animation when the colours change


class Xfce(Backend):
    name = "xfce"
    features = {"wallpaper": "xfconf (xfce4-desktop)", "live colours": "A/B GTK theme via xsettings, icons, panel, terminal",
                "transition": "X11 overlay: grow, wipe, wave, fade", "Super+W": "xfce4-keyboard-shortcuts"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.overlay = X11Overlay()

    # ---------------------------------------------------------------- xfconf

    def get(self, channel, prop):
        rc, out = self.run("xfconf-query", "-c", channel, "-p", prop)
        return out.strip() if rc == 0 else None

    def set(self, channel, prop, value, kind="string"):
        if isinstance(value, bool):
            value = "true" if value else "false"
        rc, out = self.run("xfconf-query", "-c", channel, "-p", prop, "-n", "-t", kind, "-s", str(value))
        if rc != 0:
            raise RuntimeError(f"xfconf-query {channel} {prop}: {out.strip()[:120]}")

    def read_setting(self, key):
        if key.startswith("xfconf:"):
            _, channel, prop = key.split(":", 2)
            return self.get(channel, prop)
        return super().read_setting(key)

    def restore_setting(self, key, value):
        if not key.startswith("xfconf:"):
            return super().restore_setting(key, value)
        _, channel, prop = key.split(":", 2)
        if value is None:
            self.run("xfconf-query", "-c", channel, "-p", prop, "-r")
        else:
            self.run("xfconf-query", "-c", channel, "-p", prop, "-s", value)

    # ---------------------------------------------------------------- state

    def wallpaper_props(self):
        rc, out = self.run("xfconf-query", "-c", "xfce4-desktop", "-l")
        props = [p for p in out.split() if p.endswith("/last-image")] if rc == 0 else []
        if props:
            return props
        rc, mons = self.run("xrandr", "--listmonitors")
        names = [l.split()[-1] for l in mons.splitlines()[1:]] if rc == 0 else []
        return [f"/backdrop/screen0/monitor{n}/workspace{w}/last-image" for n in (names or ["0"]) for w in range(4)]

    def current_slot(self):
        name = self.get("xsettings", "/Net/ThemeName")
        if name in (gtk.theme_name("a"), gtk.theme_name("b")):
            return name[-1]
        return None

    def current_wallpaper(self):
        for prop in self.wallpaper_props():
            v = self.get("xfce4-desktop", prop)
            if v and Path(v).is_file():
                return Path(v)
        return None

    def settings_touched(self, ctx):
        keys = [f"xfconf:xfce4-desktop:{p}" for p in self.wallpaper_props()]
        if ctx.on("apps"):
            keys.append("xfconf:xsettings:/Net/ThemeName")
        if ctx.icons:
            keys.append("xfconf:xsettings:/Net/IconThemeName")
        if self.env.has("xfce4-terminal") and ctx.on("terminal"):
            keys += [f"xfconf:xfce4-terminal:/{k}" for k in ("color-use-theme", "color-foreground", "color-background",
                                                              "color-cursor", "color-palette")]
        return keys

    def part_of(self, key):
        if key.startswith("xfconf:xfce4-terminal:"):
            return "terminal"
        if key == "xfconf:xsettings:/Net/ThemeName":
            return "apps"
        if key == "xfconf:xsettings:/Net/IconThemeName":
            return "icons"
        return super().part_of(key)

    def terminal_steps(self, ctx):
        if not (ctx.on("terminal") and self.env.has("xfce4-terminal")):
            return []
        return [("xfce4-terminal", lambda: self.terminal(ctx.theme))]

    # ---------------------------------------------------------------- applying

    def gtk_css(self, ctx):
        """The panel and notifications in the theme's colours (islands need the panel layout, so the
        panel just gets the colours here)."""
        if not ctx.on("apps"):
            return ""
        hx = hexes(ctx.theme)
        return (f"#XfcePanelWindow {{ background-color: alpha({hx['bg']}, 0.92); }}\n"
                f"#XfcePanelWindow, #XfcePanelWindow label, #XfcePanelWindow button {{ color: {hx['fg']}; }}\n"
                f"#XfcePanelWindow button:hover {{ background-color: alpha({hx['accent']}, 0.25); }}\n"
                f"#XfcePanelWindow button:checked {{ background-color: {hx['accent']}; color: {hx['on_accent']}; }}\n"
                f"#XfceNotifyWindow {{ background-color: {hx['surface']}; color: {hx['fg']};"
                f" border: 2px solid {hx['accent']}; border-radius: 8px; }}\n"
                f"#XfceNotifyWindow label#summary {{ color: {hx['accent']}; font-weight: bold; }}\n")

    def set_wallpaper(self, ctx):
        started = self.overlay.start(ctx.old, ctx.img, ctx.effect, self.env)
        for prop in self.wallpaper_props():
            self.set("xfce4-desktop", prop, str(ctx.img))
            self.set("xfce4-desktop", prop.replace("last-image", "image-style"), 5, "int")  # zoomed
        return OVERLAY_HALF if started else 0.0

    def activate(self, ctx):
        steps = []
        if ctx.on("apps"):
            steps.append(("GTK theme", lambda: self.set("xsettings", "/Net/ThemeName", gtk.theme_name(ctx.slot))))
        if ctx.icons:
            steps.append(("icons", lambda: self.set("xsettings", "/Net/IconThemeName", icons.theme_name(ctx.slot))))
        return steps + self.terminal_steps(ctx)

    def terminal(self, th):
        self.set("xfce4-terminal", "/color-use-theme", False, "bool")
        self.set("xfce4-terminal", "/color-foreground", rgb2hex(th["fg"]))
        self.set("xfce4-terminal", "/color-background", rgb2hex(th["bg"]))
        self.set("xfce4-terminal", "/color-cursor", rgb2hex(th["accent"]))
        self.set("xfce4-terminal", "/color-palette", ";".join(rgb2hex(c) for c in th["term"]))

    def finish(self):
        self.overlay.finish()

    # ---------------------------------------------------------------- Super+W

    def bind_key(self, binding, command, name):
        self.set("xfce4-keyboard-shortcuts", f"/commands/custom/{binding}", command)
        return True

    def unbind_keys(self):
        rc, out = self.run("xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-l", "-v")
        done = False
        for line in out.splitlines() if rc == 0 else []:
            prop, _, value = line.partition(" ")
            if prop.startswith("/commands/custom/") and "wallrice" in value:
                self.run("xfconf-query", "-c", "xfce4-keyboard-shortcuts", "-p", prop, "-r")
                done = True
        return done

    def doctor(self):
        ok = gtk.find_dir("themes", gtk.BASE) is not None
        return [(ok, "adw-gtk3 theme " + ("found" if ok else "missing: GTK apps keep their old look")),
                (self.env.has("xfconf-query"), "xfconf-query " + ("found" if self.env.has("xfconf-query") else "missing"))]
