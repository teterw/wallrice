"""The parts of wallrice's theme, each of which can be turned off and on again (`wallrice off PART`,
`wallrice on PART`, `wallrice parts`). Every choice is saved in state.json, so every later wallpaper
change respects it. Turning a part off puts that part's original settings back; turning it on themes
it from the current wallpaper again."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Part:
    name: str
    key: str          # its on/off in state.json (some kept their older names)
    about: str
    gnome_only: bool = False


PARTS = [
    Part("apps", "apps", "app colours: GTK and libadwaita apps, and the accent colour"),
    Part("icons", "icons", "folder icons in the accent colour (Papirus)"),
    Part("terminal", "terminal_colors", "terminal colours"),
    Part("dock", "dock", "the dock / taskbar in the theme's colours", gnome_only=True),
    Part("taskbar-icons", "dock_mono", "flat monochrome app icons in the dock / taskbar and the top bar",
         gnome_only=True),
    Part("topbar", "topbar", "the islands top bar", gnome_only=True),
    Part("transitions", "animations", "animated wallpaper changes"),
    Part("rotation", "rotation", "a new wallpaper on a timer"),
]
BY_NAME = {p.name: p for p in PARTS}
ALIASES = {"terminals": "terminal", "taskbar": "taskbar-icons", "dock-icons": "taskbar-icons",
           "app-icons": "taskbar-icons", "top-bar": "topbar", "bar": "topbar", "folders": "icons",
           "animations": "transitions", "colours": "apps", "colors": "apps", "timer": "rotation"}


def resolve(name):
    """A part from its name or an alias, or None."""
    name = (name or "").strip().lower()
    return BY_NAME.get(ALIASES.get(name, name))


def is_on(state, part):
    if isinstance(part, str):
        part = BY_NAME[part]
    return bool(state.get(part.key, True))


def enabled(state):
    """{part name: on?} for every part."""
    return {p.name: is_on(state, p) for p in PARTS}
