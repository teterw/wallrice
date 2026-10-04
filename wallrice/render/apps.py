"""Colour files for other apps, each written only when the app is installed. wallrice writes its own
file next to the app's config; `wallrice doctor` shows the line that makes the app use it."""
from .. import paths
from ..color import rgb2hex
from ..theme import hexes
from . import HEADER


def btop(theme):
    hx = hexes(theme)
    a, f, m, s2 = hx["accent"], hx["fg"], hx["muted"], hx["surface2"]
    pairs = {"main_bg": "", "main_fg": f, "title": f, "hi_fg": a, "selected_bg": s2, "selected_fg": a,
             "inactive_fg": m, "graph_text": m, "meter_bg": s2, "proc_misc": a, "cpu_box": a, "mem_box": a,
             "net_box": a, "proc_box": a, "div_line": s2, "process_start": a, "process_mid": a, "process_end": f}
    for g in ("temp", "cpu", "free", "available", "used", "download", "upload"):
        pairs.update({f"{g}_start": a, f"{g}_mid": a, f"{g}_end": f})
    pairs.update(cached_start=m, cached_mid=m, cached_end=f)
    text = f"# {HEADER}\n# use it: btop menu > Options > Color theme > wallrice\n" + "".join(
        f'theme[{k}]="{v}"\n' for k, v in pairs.items())
    return {paths.config_home() / "btop" / "themes" / "wallrice.theme": text}


def rofi(theme):
    hx = hexes(theme)
    # rofi property names can't contain "_", hence on-accent
    text = f"/* {HEADER} */\n* {{\n" + "".join(
        f"    {k.replace('_', '-')}: {hx[k]};\n" for k in ("bg", "fg", "accent", "on_accent", "surface", "surface2", "muted")) + "}\n"
    return {paths.config_home() / "rofi" / "wallrice-colors.rasi": text}


def css_colors(theme, prefix="wr"):
    hx = hexes(theme)
    return "".join(f"@define-color {prefix}_{k} {v};\n" for k, v in hx.items())


def wofi(theme):
    hx = hexes(theme)
    text = (f"/* {HEADER} */\nwindow {{ background-color: {hx['bg']}; border: 2px solid {hx['accent']}; border-radius: 12px; }}\n"
            f"#input {{ background-color: {hx['surface']}; color: {hx['fg']}; border: 1px solid {hx['surface2']}; }}\n"
            f"#entry {{ color: {hx['fg']}; }}\n#entry:selected {{ background-color: {hx['accent']}; }}\n"
            f"#entry:selected #text {{ color: {hx['on_accent']}; }}\n")
    return {paths.config_home() / "wofi" / "wallrice.css": text}


def fuzzel(theme):
    def c(k):
        return rgb2hex(theme[k])[1:] + "ff"
    text = (f"# {HEADER}\n# include it from fuzzel.ini:  include=~/.config/fuzzel/wallrice.ini\n[colors]\n"
            f"background={rgb2hex(theme['bg'])[1:]}f0\ntext={c('fg')}\nmatch={c('accent')}\n"
            f"selection={c('accent')}\nselection-text={c('on_accent')}\nselection-match={c('on_accent')}\n"
            f"border={c('accent')}\n")
    return {paths.config_home() / "fuzzel" / "wallrice.ini": text}


def waybar(theme):
    text = f"/* {HEADER} */\n/* in style.css:  @import \"wallrice.css\";  then use @wr_accent etc. */\n" + css_colors(theme)
    return {paths.config_home() / "waybar" / "wallrice.css": text}


APPS = {"btop": btop, "rofi": rofi, "wofi": wofi, "fuzzel": fuzzel, "waybar": waybar}

INCLUDES = {
    "rofi": ("rofi/config.rasi", '@import "wallrice-colors.rasi"'),
    "fuzzel": ("fuzzel/fuzzel.ini", "include=~/.config/fuzzel/wallrice.ini"),
    "waybar": ("waybar/style.css", '@import "wallrice.css";'),
    "btop": ("btop/btop.conf", 'color_theme = "wallrice"'),
}


def outputs(theme, env):
    files = {}
    for cmd, fn in APPS.items():
        if env.has(cmd):
            files.update(fn(theme))
    return files
