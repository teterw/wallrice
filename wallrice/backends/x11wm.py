"""X11 window managers without a desktop (i3, bspwm, Openbox, awesome, qtile, …).

  wallpaper      feh --bg-fill, else xwallpaper --zoom, else nitrogen, else hsetroot -cover
  transitions    the X11 overlay where the WM honours DESKTOP windows (most do)
  GTK apps       xsettingsd when it's running (live), and settings.ini (new apps)
  borders        bspwm: bspc config; i3: ~/.config/i3/wallrice (include it) and i3-msg reload
  Super+W        a line for the WM's config (printed by install and doctor)
"""
from .. import paths
from ..render import HEADER
from ..theme import hexes
from .base import Backend
from .common import X11Overlay, gtk_settings_files, first_tool, xsettingsd

OVERLAY_HALF = 0.7


class X11wm(Backend):
    name = "x11wm"
    features = {"wallpaper": "feh, xwallpaper, nitrogen or hsetroot", "live colours": "xsettingsd, WM borders",
                "transition": "X11 overlay: grow, wipe, wave, fade", "Super+W": None}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.overlay = X11Overlay()

    def outputs(self, ctx):
        hx = hexes(ctx.theme)
        files = gtk_settings_files(ctx)
        files[paths.config_home() / "i3" / "wallrice"] = (
            f"# {HEADER}\n# in i3's config:  include ~/.config/i3/wallrice\n"
            f"client.focused {hx['accent']} {hx['accent']} {hx['on_accent']} {hx['accent']} {hx['accent']}\n"
            f"client.unfocused {hx['surface']} {hx['bg']} {hx['muted']} {hx['surface']} {hx['surface']}\n")
        return files

    def set_wallpaper(self, ctx):
        started = self.overlay.start(ctx.old, ctx.img, ctx.effect, self.env)
        tool = first_tool(self.env, "feh", "xwallpaper", "nitrogen", "hsetroot")
        cmd = {"feh": ["feh", "--no-fehbg", "--bg-fill", str(ctx.img)], "xwallpaper": ["xwallpaper", "--zoom", str(ctx.img)],
               "nitrogen": ["nitrogen", "--set-zoom-fill", "--save", str(ctx.img)],
               "hsetroot": ["hsetroot", "-cover", str(ctx.img)]}.get(tool)
        if not cmd:
            ctx.notes.append("x11wm: install feh (or xwallpaper, nitrogen, hsetroot) to set the wallpaper")
            return 0.0
        rc, out = self.run(*cmd)
        if rc != 0:
            raise RuntimeError(f"{tool}: {out.strip()[:160]}")
        return OVERLAY_HALF if started else 0.0

    def activate(self, ctx):
        hx = hexes(ctx.theme)
        steps = [("GTK apps (xsettingsd)", lambda: xsettingsd(ctx, self.run))]
        if self.env.compositor == "bspwm" and self.env.has("bspc"):
            steps.append(("bspwm borders", lambda: (self.run("bspc", "config", "focused_border_color", hx["accent"]),
                                                     self.run("bspc", "config", "normal_border_color", hx["surface2"]))))
        if self.env.compositor == "i3" and self.env.has("i3-msg"):
            steps.append(("i3 borders", lambda: self.run("i3-msg", "reload")))
        return steps

    def finish(self):
        self.overlay.finish()

    def bind_hint(self, binding, command):
        if self.env.compositor == "i3":
            return f"add to i3's config:  bindsym $mod+{'Shift+' if '<Shift>' in binding else ''}w exec {command}"
        if self.env.compositor == "bspwm":
            return f"add to sxhkdrc:  super + {'shift + ' if '<Shift>' in binding else ''}w   and, indented below it:  {command}"
        return f"bind {binding} to  {command}  in your window manager's config"

    def autostart_hint(self, command):
        return f"run  {command}  from your WM's startup (e.g. i3: exec --no-startup-id {command})"
