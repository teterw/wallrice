"""GTK colours.

GTK3 programs read ~/.config/gtk-3.0/gtk.css only at startup, but re-read a *theme* whenever the theme
name changes. So the colours live in a generated theme kept in two copies, Wallrice-a and Wallrice-b:
the engine writes the one not in use and the backend switches to it, and every running GTK3 program
restyles at once. Each copy is adw-gtk3-dark (the libadwaita look for GTK3) plus colour overrides.

libadwaita (GTK4) apps don't use themes: they get the colours from ~/.config/gtk-4.0/gtk.css, as CSS
variables (libadwaita 1.6+) and @define-color (older), read when an app starts."""
from .. import paths
from ..theme import hexes
from . import HEADER, find_dir

BASE = "adw-gtk3-dark"

# libadwaita / adw-gtk3 named colours -> wallrice theme keys
NAMES = {
    "accent_color": "accent", "accent_bg_color": "accent", "accent_fg_color": "on_accent",
    "window_bg_color": "bg", "window_fg_color": "fg", "view_bg_color": "surface", "view_fg_color": "fg",
    "headerbar_bg_color": "surface", "headerbar_fg_color": "fg", "headerbar_border_color": "accent",
    "headerbar_backdrop_color": "bg", "sidebar_bg_color": "surface", "sidebar_fg_color": "fg",
    "sidebar_backdrop_color": "bg", "secondary_sidebar_bg_color": "bg", "secondary_sidebar_fg_color": "fg",
    "card_bg_color": "surface", "card_fg_color": "fg", "dialog_bg_color": "surface", "dialog_fg_color": "fg",
    "popover_bg_color": "surface2", "popover_fg_color": "fg", "thumbnail_bg_color": "surface2",
    "thumbnail_fg_color": "fg", "overview_bg_color": "bg", "overview_fg_color": "fg",
    # GTK3 names some older apps still use
    "theme_bg_color": "bg", "theme_fg_color": "fg", "theme_base_color": "surface", "theme_text_color": "fg",
    "theme_selected_bg_color": "accent", "theme_selected_fg_color": "on_accent",
}


def define_colors(theme):
    hx = hexes(theme)
    return "\n".join(f"@define-color {n} {hx[k]};" for n, k in NAMES.items())


def css_variables(theme):
    hx = hexes(theme)
    body = "".join(f"  --{n.replace('_', '-')}: {hx[k]};\n" for n, k in NAMES.items() if not n.startswith("theme_"))
    return ":root {\n" + body + "}"


def theme_name(slot):
    return f"Wallrice-{slot}"


def gtk3_theme(theme, slot):
    """The A/B GTK theme: {path: text}. Without adw-gtk3 installed, GTK's own Adwaita dark is the base
    (the colours then only reach selections and accents; `wallrice doctor` says to install adw-gtk3)."""
    root = paths.data_home() / "themes" / theme_name(slot)
    base = find_dir("themes", BASE)
    files = {}
    for ver in ("gtk-3.0", "gtk-4.0"):
        if base and (base / ver / "gtk.css").exists():
            imp = f'@import url("file://{base / ver / "gtk.css"}");\n'
        elif ver == "gtk-3.0":
            imp = '@import url("resource:///org/gtk/libgtk/theme/Adwaita/gtk-contained-dark.css");\n'
        else:
            imp = ""
        css = f"/* {HEADER} */\n{imp}{define_colors(theme)}\n"
        if ver == "gtk-4.0":
            css += css_variables(theme) + "\n"
        files[root / ver / "gtk.css"] = css
        files[root / ver / "gtk-dark.css"] = css
    files[root / "index.theme"] = (
        "[Desktop Entry]\nType=X-GNOME-Metatheme\nName=Wallrice\n"
        f"Comment={BASE} coloured from the wallpaper (wallrice)\nEncoding=UTF-8\n\n"
        f"[X-GNOME-Metatheme]\nGtkTheme={theme_name(slot)}\n")
    return files


def gtk4_user_css(theme):
    return f"/* {HEADER} */\n{define_colors(theme)}\n{css_variables(theme)}\n"


def outputs(theme, slot):
    files = gtk3_theme(theme, slot)
    files[paths.config_home() / "gtk-4.0" / "gtk.css"] = gtk4_user_css(theme)
    return files
