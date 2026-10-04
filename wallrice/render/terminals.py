"""Terminal colours, most portable first:

1. escape sequences (OSC 4/10/11/12) written to every terminal the user has open: VTE (Ptyxis, GNOME
   Terminal, Tilix, xfce4-terminal), kitty, alacritty, foot, wezterm, Konsole and xterm windows change
   at once (the pywal/wallust way);
2. each installed terminal's own colour file, for new windows. Where the terminal can include a file
   (kitty, alacritty, foot, wezterm) wallrice writes only its own file; `wallrice doctor` shows the line
   to add to the main config if it isn't there yet."""
import os
import stat
from pathlib import Path

from .. import paths
from ..color import rgb2hex
from . import HEADER


def osc(theme):
    t = [rgb2hex(c) for c in theme["term"]]
    seq = "".join(f"\033]4;{i};{h}\033\\" for i, h in enumerate(t))
    seq += f"\033]10;{rgb2hex(theme['fg'])}\033\\\033]11;{rgb2hex(theme['bg'])}\033\\"
    seq += f"\033]12;{rgb2hex(theme['accent'])}\033\\"
    seq += f"\033]708;{rgb2hex(theme['bg'])}\033\\"  # urxvt's border
    return seq


def open_terminals(uid=None, pts=Path("/dev/pts")):
    """Every pseudo-terminal the user owns."""
    uid = os.getuid() if uid is None else uid
    out = []
    try:
        entries = sorted(pts.iterdir())
    except OSError:
        return out
    for p in entries:
        if not p.name.isdigit():
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        if st.st_uid == uid and stat.S_ISCHR(st.st_mode):
            out.append(p)
    return out


def send_osc(theme, terminals=None):
    """Write the sequences to every open terminal. Returns how many took them."""
    seq = osc(theme).encode()
    n = 0
    for p in open_terminals() if terminals is None else terminals:
        try:
            fd = os.open(p, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            os.write(fd, seq)
            n += 1
        except OSError:
            pass
        finally:
            os.close(fd)
    return n


def ptyxis_palette(theme, slot):
    """Ptyxis (GNOME's terminal) palettes: ~/.local/share/org.gnome.Ptyxis/palettes/<id>.palette.
    The A/B pair makes running windows switch too, like the GTK theme."""
    t = [rgb2hex(c) for c in theme["term"]]
    text = (f"# {HEADER}\n[Palette]\nName=Wallrice\n"
            f"Background={rgb2hex(theme['bg'])}\nForeground={rgb2hex(theme['fg'])}\nCursor={rgb2hex(theme['accent'])}\n"
            + "".join(f"Color{i}={h}\n" for i, h in enumerate(t)))
    return {paths.data_home() / "org.gnome.Ptyxis" / "palettes" / f"wallrice-{slot}.palette": text}


def kitty(theme):
    t = [rgb2hex(c) for c in theme["term"]]
    hx = {k: rgb2hex(theme[k]) for k in ("bg", "fg", "accent", "on_accent", "surface2")}
    text = (f"# {HEADER}\n# include it from kitty.conf:  include wallrice.conf\n"
            f"foreground {hx['fg']}\nbackground {hx['bg']}\ncursor {hx['accent']}\n"
            f"selection_background {hx['accent']}\nselection_foreground {hx['on_accent']}\n"
            f"active_border_color {hx['accent']}\ninactive_border_color {hx['surface2']}\n"
            f"active_tab_background {hx['accent']}\nactive_tab_foreground {hx['on_accent']}\n"
            + "".join(f"color{i} {h}\n" for i, h in enumerate(t)))
    return {paths.config_home() / "kitty" / "wallrice.conf": text}


def alacritty(theme):
    t = [rgb2hex(c) for c in theme["term"]]
    names = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")
    text = (f"# {HEADER}\n# import it from alacritty.toml:  [general] import = [\"~/.config/alacritty/wallrice.toml\"]\n"
            f"[colors.primary]\nbackground = \"{rgb2hex(theme['bg'])}\"\nforeground = \"{rgb2hex(theme['fg'])}\"\n\n"
            f"[colors.cursor]\ncursor = \"{rgb2hex(theme['accent'])}\"\ntext = \"{rgb2hex(theme['on_accent'])}\"\n\n"
            "[colors.normal]\n" + "".join(f"{n} = \"{t[i]}\"\n" for i, n in enumerate(names)) +
            "\n[colors.bright]\n" + "".join(f"{n} = \"{t[i + 8]}\"\n" for i, n in enumerate(names)))
    return {paths.config_home() / "alacritty" / "wallrice.toml": text}


def foot(theme):
    t = [rgb2hex(c)[1:] for c in theme["term"]]
    text = (f"# {HEADER}\n# include it from foot.ini:  include=~/.config/foot/wallrice.ini\n[colors]\n"
            f"background={rgb2hex(theme['bg'])[1:]}\nforeground={rgb2hex(theme['fg'])[1:]}\n"
            f"cursor={rgb2hex(theme['on_accent'])[1:]} {rgb2hex(theme['accent'])[1:]}\n"
            + "".join(f"regular{i}={t[i]}\n" for i in range(8)) + "".join(f"bright{i}={t[i + 8]}\n" for i in range(8)))
    return {paths.config_home() / "foot" / "wallrice.ini": text}


def wezterm(theme):
    t = [rgb2hex(c) for c in theme["term"]]
    q = lambda xs: "[" + ", ".join(f'"{x}"' for x in xs) + "]"  # noqa: E731
    text = (f"# {HEADER}\n# use it from wezterm.lua:  config.color_scheme = \"wallrice\"\n[colors]\n"
            f"background = \"{rgb2hex(theme['bg'])}\"\nforeground = \"{rgb2hex(theme['fg'])}\"\n"
            f"cursor_bg = \"{rgb2hex(theme['accent'])}\"\ncursor_border = \"{rgb2hex(theme['accent'])}\"\n"
            f"selection_bg = \"{rgb2hex(theme['accent'])}\"\nselection_fg = \"{rgb2hex(theme['on_accent'])}\"\n"
            f"ansi = {q(t[:8])}\nbrights = {q(t[8:])}\n\n[metadata]\nname = \"wallrice\"\n")
    return {paths.config_home() / "wezterm" / "colors" / "wallrice.toml": text}


def konsole(theme):
    t = theme["term"]

    def rgb(c):
        return ",".join(str(round(max(0, min(1, x)) * 255)) for x in c)
    body = f"# {HEADER}\n[General]\nDescription=Wallrice\nOpacity=1\n\n"
    body += f"[Background]\nColor={rgb(theme['bg'])}\n\n[BackgroundIntense]\nColor={rgb(theme['bg'])}\n\n"
    body += f"[Foreground]\nColor={rgb(theme['fg'])}\n\n[ForegroundIntense]\nColor={rgb(theme['fg'])}\n\n"
    for i in range(8):
        body += f"[Color{i}]\nColor={rgb(t[i])}\n\n[Color{i}Intense]\nColor={rgb(t[i + 8])}\n\n"
    return {paths.data_home() / "konsole" / "Wallrice.colorscheme": body}


# terminal command -> renderer (only installed terminals get a file)
FILES = {"kitty": kitty, "alacritty": alacritty, "foot": foot, "wezterm": wezterm, "konsole": konsole}

# lines that make each terminal's main config use our file (doctor checks them)
INCLUDES = {
    "kitty": ("kitty/kitty.conf", "include wallrice.conf"),
    "alacritty": ("alacritty/alacritty.toml", '[general]\nimport = ["~/.config/alacritty/wallrice.toml"]'),
    "foot": ("foot/foot.ini", "include=~/.config/foot/wallrice.ini"),
    "wezterm": ("wezterm/wezterm.lua", 'config.color_scheme = "wallrice"'),
}


def outputs(theme, env, slot):
    files = {}
    if env.has("ptyxis"):
        files.update(ptyxis_palette(theme, slot))
    for cmd, fn in FILES.items():
        if env.has(cmd):
            files.update(fn(theme))
    return files
