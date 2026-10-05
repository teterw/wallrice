"""Cinnamon and MATE: GTK desktops configured through dconf, mostly on X11.

  wallpaper      Cinnamon: org.cinnamon.desktop.background picture-uri; MATE: org.mate.background
                 picture-filename; both zoomed
  GTK apps       the desktop's interface gtk-theme Wallrice-a|b (live, via its settings daemon)
  icons          the desktop's interface icon-theme Wallrice-Papirus-a|b
  transitions    the X11 overlay on X11 (grow / wipe / wave / fade); the desktop's own fade otherwise
  Super+W        the desktop's custom keybindings in dconf
"""
from pathlib import Path

from ..render import gtk, icons
from .base import Backend, gv_list, gv_str, gv_strip
from .common import X11Overlay

OVERLAY_HALF = 0.7


class GsettingsDesktop(Backend):
    BG = IFACE = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.overlay = X11Overlay()

    def wallpaper_keys(self, img):
        raise NotImplementedError

    def theme_keys(self, ctx):
        keys = {f"{self.IFACE}/gtk-theme": gv_str(gtk.theme_name(ctx.slot))} if ctx.on("apps") else {}
        if ctx.icons:
            keys[f"{self.IFACE}/icon-theme"] = gv_str(icons.theme_name(ctx.slot))
        return keys

    def current_slot(self):
        name = gv_strip(self.read(f"{self.IFACE}/gtk-theme"))
        return name[-1] if name in (gtk.theme_name("a"), gtk.theme_name("b")) else None

    def settings_touched(self, ctx):
        return sorted({**self.wallpaper_keys(ctx.img), **self.theme_keys(ctx)})

    def set_wallpaper(self, ctx):
        started = self.overlay.start(ctx.old, ctx.img, ctx.effect, self.env)
        self.load(self.wallpaper_keys(ctx.img))
        return OVERLAY_HALF if started else 0.0

    def part_of(self, key):
        if key == f"{self.IFACE}/gtk-theme":
            return "apps"
        if key == f"{self.IFACE}/icon-theme":
            return "icons"
        return super().part_of(key)

    def activate(self, ctx):
        keys = self.theme_keys(ctx)
        return [(f"{self.name} theme and icons", lambda: self.load(keys))] if keys else []

    def finish(self):
        self.overlay.finish()


class Cinnamon(GsettingsDesktop):
    name = "cinnamon"
    features = {"wallpaper": "org.cinnamon.desktop.background", "live colours": "A/B GTK theme, icons",
                "transition": "X11 overlay: grow, wipe, wave, fade", "Super+W": "custom keybinding"}
    BG = "/org/cinnamon/desktop/background"
    IFACE = "/org/cinnamon/desktop/interface"
    KEYS = "/org/cinnamon/desktop/keybindings"

    def wallpaper_keys(self, img):
        return {f"{self.BG}/picture-uri": gv_str(Path(img).as_uri()), f"{self.BG}/picture-options": gv_str("zoom")}

    def current_wallpaper(self):
        uri = gv_strip(self.read(f"{self.BG}/picture-uri"))
        if uri and uri.startswith("file://"):
            from urllib.parse import unquote, urlparse
            return Path(unquote(urlparse(uri).path))
        return None

    def bind_key(self, binding, command, name):
        custom = gv_list(self.read(f"{self.KEYS}/custom-list"))
        if name not in custom:
            custom.append(name)
        path = f"{self.KEYS}/custom-keybindings/{name}/"
        self.load({f"{self.KEYS}/custom-list": "[" + ", ".join(gv_str(c) for c in custom) + "]",
                   f"{path}name": gv_str(name), f"{path}command": gv_str(command),
                   f"{path}binding": f"[{gv_str(binding)}]"})
        return True

    def unbind_keys(self):
        custom = gv_list(self.read(f"{self.KEYS}/custom-list"))
        mine = [c for c in custom if c.startswith("wallrice")]
        if not mine:
            return False
        rest = [c for c in custom if c not in mine]
        self.load({f"{self.KEYS}/custom-list": "[" + ", ".join(gv_str(c) for c in rest) + "]" if rest else "@as []"})
        for c in mine:
            self.run("dconf", "reset", "-f", f"{self.KEYS}/custom-keybindings/{c}/")
        return True


class Mate(GsettingsDesktop):
    name = "mate"
    features = {"wallpaper": "org.mate.background", "live colours": "A/B GTK theme, icons",
                "transition": "X11 overlay: grow, wipe, wave, fade", "Super+W": "custom keybinding"}
    BG = "/org/mate/desktop/background"
    IFACE = "/org/mate/desktop/interface"
    KEYS = "/org/mate/desktop/keybindings"

    def wallpaper_keys(self, img):
        return {f"{self.BG}/picture-filename": gv_str(str(img)), f"{self.BG}/picture-options": gv_str("zoom")}

    def current_wallpaper(self):
        v = gv_strip(self.read(f"{self.BG}/picture-filename"))
        return Path(v) if v else None

    def bind_key(self, binding, command, name):
        path = f"{self.KEYS}/{name}/"
        self.load({f"{path}name": gv_str(name), f"{path}action": gv_str(command), f"{path}binding": gv_str(binding)})
        return True

    def unbind_keys(self):
        for name in ("wallrice-pick", "wallrice-random"):
            self.run("dconf", "reset", "-f", f"{self.KEYS}/{name}/")
        return True
