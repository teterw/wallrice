"""Folder icons in the wallpaper's colour: a per-user icon theme that inherits Papirus-Dark and only
re-points the folder icons to the Papirus colour nearest the accent (what papirus-folders does,
without root and without touching the system theme). A/B copies like the GTK theme, so running
programs pick up the change when the backend switches to the fresh copy."""
import os
from pathlib import Path

from .. import paths
from ..theme import nearest
from . import find_dir

# Papirus folder colours and their approximate RGB, to pick the one nearest the accent
PAPIRUS = {"blue": "#5294e2", "bluegrey": "#607d8b", "brown": "#ae8e6c", "cyan": "#00bcd4", "darkcyan": "#45abb7",
           "deeporange": "#eb6637", "green": "#87b158", "grey": "#8e8e8e", "indigo": "#5c6bc0", "magenta": "#ca71df",
           "orange": "#ee923a", "pink": "#f06292", "red": "#e25252", "teal": "#16a085", "violet": "#7e57c2",
           "yellow": "#f9bd30", "palebrown": "#d1bfae", "paleorange": "#eecaab", "carmine": "#a30002", "nordic": "#81a1c1"}


def theme_name(slot):
    return f"Wallrice-Papirus-{slot}"


def papirus_base():
    return find_dir("icons", "Papirus")


def available_colors(base):
    places = base / "48x48" / "places"
    return {n: h for n, h in PAPIRUS.items() if (places / f"folder-{n}.svg").exists()}


def plan(accent, slot):
    """The overlay as {"links": {path: target}, "files": {path: text}, "root": dir, "color": name},
    or None without Papirus."""
    base = papirus_base()
    if base is None:
        return None
    colors = available_colors(base) or {"blue": PAPIRUS["blue"]}
    color = nearest(accent, colors)
    root = paths.data_home() / "icons" / theme_name(slot)
    links, dirs = {}, []
    sizes = [p for p in base.iterdir() if p.is_dir() and (p / "places").is_dir()
             and (p.name == "symbolic" or (p.name[0].isdigit() and "@" not in p.name))]
    for size_dir in sorted(sizes):
        for link in (size_dir / "places").iterdir():
            if not link.is_symlink():
                continue
            # Follow the whole chain (folder-videos -> folder-blue-videos, some via a second link)
            target = Path(os.path.realpath(link)).name
            if "-blue" in target:  # Papirus' default folder colour
                new = size_dir / "places" / target.replace("-blue", f"-{color}")
                if new.exists():
                    links[root / size_dir.name / "places" / link.name] = new
        dirs.append(f"{size_dir.name}/places")
    sections = "".join(
        f"[{d}]\nContext=Places\nSize={int(d.split('x')[0])}\nType=Fixed\n\n" if d[0].isdigit()
        else f"[{d}]\nContext=Places\nSize=48\nType=Scalable\nMinSize=8\nMaxSize=512\n\n" for d in dirs)
    # Papirus-Dark is complete on its own: also inheriting Papirus would make every GTK program index
    # that theme too (hundreds of folders, tens of MB of RAM each without an icon cache)
    index = (f"[Icon Theme]\nName={theme_name(slot)}\nComment=Papirus-Dark with folders in the wallpaper's colour (wallrice)\n"
             f"Inherits=Papirus-Dark,hicolor\nDirectories={','.join(dirs)}\n\n{sections}")
    return {"links": links, "files": {root / "index.theme": index}, "root": root, "color": color}
