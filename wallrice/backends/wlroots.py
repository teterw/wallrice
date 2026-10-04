"""wlroots compositors: Hyprland, Sway, river, Wayfire, niri, labwc (the Arch-rice way).

  wallpaper      swww (best: animated), else swaybg, else hyprpaper
  transitions    swww's own: grow from the pointer (hyprctl cursorpos), wipe, wave, fade
  GTK apps       the A/B GTK theme over dconf (GTK on Wayland reads it live) and settings.ini
  borders        Hyprland: hyprctl keyword general:col.active_border; Sway: swaymsg client.focused;
                 plus ~/.config/hypr/wallrice.conf and ~/.config/sway/wallrice to include from configs
  bar            waybar: ~/.config/waybar/wallrice.css, reloaded with SIGUSR2
  Super+W        a line for the compositor's config (printed by install and doctor)
"""
import subprocess
import time

from .. import paths
from ..render import HEADER
from ..theme import hexes
from .base import Backend
from .common import dconf_interface_keys, gtk_settings_files, first_tool

SWWW_FX = {"grow": "grow", "wipe": "wipe", "wave": "wave", "fade": "fade", "random": "random", "none": "none"}


class Wlroots(Backend):
    name = "wlroots"
    features = {"wallpaper": "swww, swaybg or hyprpaper", "live colours": "GTK theme, borders, waybar",
                "transition": "swww: grow, wipe, wave, fade", "Super+W": None}

    @property
    def wm(self):
        d = set(self.env.desktops) | {self.env.compositor}
        return "hyprland" if "hyprland" in d else "sway" if "sway" in d else next(iter(d - {""}), "wlroots")

    def outputs(self, ctx):
        hx = hexes(ctx.theme)
        files = gtk_settings_files(ctx)
        hl = "".join(f"$wr_{k} = rgb({v[1:]})\n" for k, v in hx.items())
        files[paths.config_home() / "hypr" / "wallrice.conf"] = (
            f"# {HEADER}\n# in hyprland.conf:  source = ~/.config/hypr/wallrice.conf\n{hl}"
            "general {\n    col.active_border = $wr_accent\n    col.inactive_border = $wr_surface2\n}\n")
        files[paths.config_home() / "sway" / "wallrice"] = (
            f"# {HEADER}\n# in sway's config:  include ~/.config/sway/wallrice\n" + self.sway_colors(hx))
        return files

    @staticmethod
    def sway_colors(hx):
        return (f"client.focused {hx['accent']} {hx['accent']} {hx['on_accent']} {hx['accent']} {hx['accent']}\n"
                f"client.focused_inactive {hx['surface2']} {hx['surface']} {hx['fg']} {hx['surface2']} {hx['surface2']}\n"
                f"client.unfocused {hx['surface']} {hx['bg']} {hx['muted']} {hx['surface']} {hx['surface']}\n")

    # ---------------------------------------------------------------- wallpaper

    def cursor(self):
        if self.wm == "hyprland":
            rc, out = self.run("hyprctl", "cursorpos")
            if rc == 0 and "," in out:
                x, y = (v.strip() for v in out.split(",")[:2])
                return f"{x},{y}"
        return None

    def set_wallpaper(self, ctx):
        if self.env.has("swww"):
            if self.run("swww", "query")[0] != 0:  # the daemon isn't running yet
                subprocess.Popen(["swww-daemon"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                for _ in range(20):
                    if self.run("swww", "query")[0] == 0:
                        break
                    time.sleep(0.1)
            fx = SWWW_FX.get(ctx.effect, "random")
            args = ["swww", "img", str(ctx.img), "--transition-type", fx, "--transition-duration", "1.3",
                    "--transition-fps", "60"]
            pos = self.cursor()
            if pos and fx in ("grow", "random"):
                args += ["--transition-pos", pos, "--invert-y"]
            rc, out = self.run(*args)
            if rc != 0:
                raise RuntimeError(f"swww: {out.strip()[:160]}")
            ctx.settle = 0.0 if fx == "none" else 1.3
            return 0.0 if fx == "none" else 0.65
        if self.env.has("swaybg"):
            self.run("pkill", "-x", "swaybg")
            subprocess.Popen(["swaybg", "-m", "fill", "-i", str(ctx.img)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return 0.0
        if self.env.has("hyprctl") and self.wm == "hyprland":
            self.run("hyprctl", "hyprpaper", "preload", str(ctx.img))
            self.run("hyprctl", "hyprpaper", "wallpaper", f",{ctx.img}")
            return 0.0
        ctx.notes.append("wlroots: install swww (best), swaybg or hyprpaper to set the wallpaper")
        return 0.0

    # ---------------------------------------------------------------- colours

    def activate(self, ctx):
        hx = hexes(ctx.theme)
        steps = []
        if self.env.has("dconf"):
            steps.append(("GTK apps", lambda: self.load(dconf_interface_keys(ctx))))
        if self.wm == "hyprland" and self.env.has("hyprctl"):
            steps.append(("Hyprland borders", lambda: (
                self.run("hyprctl", "keyword", "general:col.active_border", f"rgb({hx['accent'][1:]})"),
                self.run("hyprctl", "keyword", "general:col.inactive_border", f"rgb({hx['surface2'][1:]})"))))
        if self.wm == "sway" and self.env.has("swaymsg"):
            steps.append(("Sway borders", lambda: [self.run("swaymsg", *line.split())
                                                   for line in self.sway_colors(hx).splitlines()]))
        if self.env.has("waybar"):
            steps.append(("waybar", lambda: self.run("pkill", "-SIGUSR2", "-x", "waybar")))
        return steps

    # ---------------------------------------------------------------- hints

    def bind_hint(self, binding, command):
        mods = "SUPER SHIFT" if "<Shift>" in binding else "SUPER"
        if self.wm == "hyprland":
            return f"add to hyprland.conf:  bind = {mods.replace(' ', '_')}, W, exec, {command}"
        sway_mods = "$mod+Shift" if "<Shift>" in binding else "$mod"
        return f"add to your compositor config, e.g. sway:  bindsym {sway_mods}+w exec {command}"

    def autostart_hint(self, command):
        if self.wm == "hyprland":
            return f"exec-once = swww-daemon & {command}"
        return f"exec swww-daemon; exec {command}"

    def doctor(self):
        tool = first_tool(self.env, "swww", "swaybg", "hyprpaper")
        return [(True if tool == "swww" else (None if tool else False),
                 f"wallpaper tool: {tool or 'none'}" + ("" if tool == "swww" else "  (swww gives the animated changes)"))]
