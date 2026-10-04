"""LXQt (X11, or Wayland with LXQt 2).

  wallpaper      pcmanfm-qt --set-wallpaper FILE --wallpaper-mode=zoom
  Qt apps        the palette in ~/.config/lxqt/lxqt.conf (LXQt watches the file and recolours)
  GTK apps       ~/.config/gtk-3.0/settings.ini (new apps), dconf where available
  icons          lxqt.conf icon_theme Wallrice-Papirus-a|b
  transitions    the X11 overlay on X11
  Super+W        ~/.config/lxqt/globalkeyshortcuts.conf (read by lxqt-globalkeysd at login)
"""
from .. import paths
from ..color import rgb2hex
from ..render import icons
from .base import Backend
from .common import X11Overlay, dconf_interface_keys, gtk_settings_files, ini_set, ini_update

OVERLAY_HALF = 0.7


def lxqt_conf():
    return paths.config_home() / "lxqt" / "lxqt.conf"


class Lxqt(Backend):
    name = "lxqt"
    features = {"wallpaper": "pcmanfm-qt", "live colours": "Qt palette, GTK settings, icons",
                "transition": "X11 overlay on X11", "Super+W": "lxqt-globalkeysd (after re-login)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.overlay = X11Overlay()

    def outputs(self, ctx):
        th = ctx.theme
        palette = {"window_color": rgb2hex(th["bg"]), "base_color": rgb2hex(th["surface"]),
                   "alternate_base_color": rgb2hex(th["surface2"]), "highlight_color": rgb2hex(th["accent"]),
                   "highlighted_text_color": rgb2hex(th["on_accent"]), "window_text_color": rgb2hex(th["fg"]),
                   "text_color": rgb2hex(th["fg"]), "link_color": rgb2hex(th["accent"]),
                   "link_visited_color": rgb2hex(th["muted"])}
        conf = lxqt_conf()
        text = ini_update(conf, "Palette", palette)
        if ctx.icons:
            text = ini_set(text, "General", {"icon_theme": icons.theme_name(ctx.slot)})
        files = {conf: text}
        files.update(gtk_settings_files(ctx))
        return files

    def set_wallpaper(self, ctx):
        started = self.overlay.start(ctx.old, ctx.img, ctx.effect, self.env)
        rc, out = self.run("pcmanfm-qt", f"--set-wallpaper={ctx.img}", "--wallpaper-mode=zoom")
        if rc != 0:
            raise RuntimeError(f"pcmanfm-qt: {out.strip()[:160]}")
        return OVERLAY_HALF if started else 0.0

    def activate(self, ctx):
        return [("GTK apps", lambda: self.load(dconf_interface_keys(ctx)))] if self.env.has("dconf") else []

    def finish(self):
        self.overlay.finish()

    def bind_key(self, binding, command, name):
        conf = paths.config_home() / "lxqt" / "globalkeyshortcuts.conf"
        key = binding.replace("<Super>", "Meta%2B").replace("<Shift>", "Shift%2B").replace("w", "W")
        exe, _, args = command.partition(" ")
        text = ini_update(conf, f"{key}.wallrice", {"Comment": name, "Enabled": "true",
                                                    "Exec": ", ".join([exe, *args.split()])})
        conf.parent.mkdir(parents=True, exist_ok=True)
        conf.write_text(text)
        return True

