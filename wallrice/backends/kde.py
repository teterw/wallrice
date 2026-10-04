"""KDE Plasma 5/6 (Wayland and X11).

  wallpaper      plasma-apply-wallpaperimage (Plasma cross-fades it)
  colours        a generated colour scheme in two copies, Wallrice-a and Wallrice-b, applied with
                 plasma-apply-colorscheme (it won't re-apply the scheme already in use, hence A/B),
                 with the wallpaper's accent
  icons          plasma-changeicons Wallrice-Papirus-a|b
  GTK apps       the A/B GTK theme over dconf (Wayland) and xsettingsd (X11), and settings.ini
  terminal       Konsole colour scheme "Wallrice"; escape sequences for open windows
  Super+W        not set automatically: System Settings > Keyboard > Shortcuts
"""
import re
import shutil
from pathlib import Path

from .. import paths
from ..color import mix, rgb255
from ..render import HEADER, icons
from .base import Backend
from .common import dconf_interface_keys, gtk_settings_files, first_tool, xsettingsd

LIBEXEC = ("/usr/libexec", "/usr/lib/x86_64-linux-gnu/libexec", "/usr/lib/aarch64-linux-gnu/libexec",
           "/usr/lib/libexec", "/usr/lib64/libexec", "/usr/lib")


def scheme_name(slot):
    return f"Wallrice-{slot}"


def color_scheme(th, slot):
    """A KDE colour scheme (.colors) from the theme."""
    def c(rgb):
        return ",".join(str(v) for v in rgb255(rgb))
    bg, fg, acc, on = th["bg"], th["fg"], th["accent"], th["on_accent"]
    s1, s2, muted, term = th["surface"], th["surface2"], th["muted"], th["term"]
    common = {"DecorationFocus": c(acc), "DecorationHover": c(acc), "ForegroundActive": c(acc),
              "ForegroundInactive": c(muted), "ForegroundLink": c(acc), "ForegroundNegative": c(term[1]),
              "ForegroundNeutral": c(term[3]), "ForegroundNormal": c(fg), "ForegroundPositive": c(term[2]),
              "ForegroundVisited": c(mix(acc, fg, 0.4))}
    groups = {"Window": (bg, s1), "View": (s1, bg), "Button": (s2, s1), "Header": (s1, bg),
              "Tooltip": (s2, s1), "Complementary": (bg, s1)}
    out = [f"# {HEADER}", "[General]", f"ColorScheme={scheme_name(slot)}", "Name=Wallrice", "shadeSortColumn=true", "",
           "[KDE]", "contrast=4", ""]
    for g, (normal, alt) in groups.items():
        out += [f"[Colors:{g}]", f"BackgroundNormal={c(normal)}", f"BackgroundAlternate={c(alt)}"]
        out += [f"{k}={v}" for k, v in common.items()] + [""]
    out += ["[Colors:Selection]", f"BackgroundNormal={c(acc)}", f"BackgroundAlternate={c(mix(acc, bg, 0.3))}"]
    out += [f"{k}={v}" for k, v in {**common, "ForegroundNormal": c(on), "ForegroundActive": c(on)}.items()] + [""]
    out += ["[WM]", f"activeBackground={c(s1)}", f"activeForeground={c(fg)}", f"activeBlend={c(acc)}",
            f"inactiveBackground={c(bg)}", f"inactiveForeground={c(muted)}", f"inactiveBlend={c(bg)}", ""]
    return "\n".join(out) + "\n"


class Kde(Backend):
    name = "kde"
    features = {"wallpaper": "plasma-apply-wallpaperimage", "live colours": "A/B colour scheme with accent, icons, GTK apps",
                "transition": "Plasma's own cross-fade", "Super+W": "by hand in System Settings (install says where)"}

    def kread(self, group, key, file="kdeglobals"):
        tool = first_tool(self.env, "kreadconfig6", "kreadconfig5")
        if not tool:
            return None
        rc, out = self.run(tool, "--file", file, "--group", group, "--key", key)
        return out.strip() if rc == 0 and out.strip() else None

    def current_slot(self):
        name = self.kread("General", "ColorScheme")
        return name[-1] if name in (scheme_name("a"), scheme_name("b")) else None

    def current_wallpaper(self):
        rc_file = paths.config_home() / "plasma-org.kde.plasma.desktop-appletsrc"
        try:
            m = re.findall(r"^Image=(?:file://)?(.+)$", rc_file.read_text(errors="replace"), re.M)
        except OSError:
            return None
        for v in m:
            if Path(v).is_file():
                return Path(v)
        return None

    def read_setting(self, key):
        if key == "kde:colorscheme":
            return self.kread("General", "ColorScheme")
        if key == "kde:icons":
            return self.kread("Icons", "Theme")
        if key == "kde:wallpaper":
            w = self.current_wallpaper()
            return str(w) if w else None
        return super().read_setting(key)

    def restore_setting(self, key, value):
        if key == "kde:colorscheme" and value:
            self.run("plasma-apply-colorscheme", value)
        elif key == "kde:icons" and value and self.changeicons():
            self.run(self.changeicons(), value)
        elif key == "kde:wallpaper" and value:
            self.run("plasma-apply-wallpaperimage", value)
        elif key.startswith("/"):
            super().restore_setting(key, value)

    def settings_touched(self, ctx):
        keys = ["kde:colorscheme", "kde:icons", "kde:wallpaper"]
        if self.env.has("dconf"):
            keys += list(dconf_interface_keys(ctx))
        return keys

    def changeicons(self):
        found = shutil.which("plasma-changeicons")
        if found:
            return found
        for d in LIBEXEC:
            p = Path(d) / "plasma-changeicons"
            if p.is_file():
                return str(p)
        return None

    def outputs(self, ctx):
        files = {paths.data_home() / "color-schemes" / f"{scheme_name(ctx.slot)}.colors": color_scheme(ctx.theme, ctx.slot)}
        files.update(gtk_settings_files(ctx))
        return files

    def set_wallpaper(self, ctx):
        rc, out = self.run("plasma-apply-wallpaperimage", str(ctx.img))
        if rc != 0:
            raise RuntimeError(f"plasma-apply-wallpaperimage: {out.strip()[:160]}")
        ctx.settle = 1.0
        return 0.5

    def activate(self, ctx):
        acc = "#%02x%02x%02x" % rgb255(ctx.theme["accent"])
        steps = [("colour scheme", lambda: self.apply_scheme(ctx.slot, acc))]
        if ctx.icons and self.changeicons():
            steps.append(("icons", lambda: self.run(self.changeicons(), icons.theme_name(ctx.slot))))
        if self.env.has("dconf"):
            steps.append(("GTK apps", lambda: self.load(dconf_interface_keys(ctx))))
        if self.env.session == "x11":
            steps.append(("GTK apps (xsettingsd)", lambda: xsettingsd(ctx, self.run)))
        return steps

    def apply_scheme(self, slot, accent):
        """The scheme, then the accent: given both at once, Plasma 6 applies only the accent."""
        rc, out = self.run("plasma-apply-colorscheme", scheme_name(slot))
        if rc != 0:
            raise RuntimeError(f"plasma-apply-colorscheme: {out.strip()[:160]}")
        self.run("plasma-apply-colorscheme", "--accent-color", accent)  # Plasma 5.26+; older ones ignore it

    def bind_hint(self, binding, command):
        key = binding.replace("<Super>", "Meta+").replace("<Shift>", "Shift+").replace("w", "W")
        return f"System Settings > Keyboard > Shortcuts > Add New > Command: {command}, shortcut {key}"

    def doctor(self):
        out = [(self.env.has("plasma-apply-colorscheme"), "plasma-apply-colorscheme " +
                ("found" if self.env.has("plasma-apply-colorscheme") else "missing: colours can't be applied"))]
        out.append((True if self.changeicons() else None, "plasma-changeicons " +
                    ("found" if self.changeicons() else "not found: folder colours apply at next login")))
        return out
