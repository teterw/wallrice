"""What is this machine running? Detect, don't assume: the desktop ($XDG_CURRENT_DESKTOP may be a
":"-separated list), the session type, a running wlroots compositor, the distro and its package
manager, and every optional tool."""
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .sh import run

WLROOTS = ("hyprland", "sway", "river", "wayfire", "niri", "labwc")
X11_WMS = ("i3", "bspwm", "openbox", "awesome", "herbstluftwm", "qtile", "xmonad", "dwm", "fluxbox", "icewm")

PKG = {"fedora": "dnf", "rhel": "dnf", "centos": "dnf", "debian": "apt", "ubuntu": "apt", "arch": "pacman",
       "opensuse": "zypper", "suse": "zypper", "void": "xbps-install", "alpine": "apk", "gentoo": "emerge",
       "solus": "eopkg", "nixos": "nix-env"}

# Package names per package manager (check with the package manager before installing)
PACKAGES = {
    "pygobject": {"dnf": ["python3-gobject"], "apt": ["python3-gi", "python3-gi-cairo", "gir1.2-gtk-3.0"],
                  "pacman": ["python-gobject"], "zypper": ["python3-gobject", "python3-gobject-cairo", "typelib-1_0-Gtk-3_0"]},
    "cairo": {"dnf": ["python3-cairo"], "apt": ["python3-cairo"], "pacman": ["python-cairo"], "zypper": ["python3-cairo"]},
    "pillow": {"dnf": ["python3-pillow"], "apt": ["python3-pil"], "pacman": ["python-pillow"], "zypper": ["python3-Pillow"]},
    "git": {"*": ["git"]},
    "papirus": {"*": ["papirus-icon-theme"]},
    "adw-gtk3": {"dnf": ["adw-gtk3-theme"], "pacman": ["adw-gtk-theme"], "zypper": ["adw-gtk3"]},
}


@dataclass
class Env:
    desktops: list = field(default_factory=list)  # lowercased, e.g. ["ubuntu", "gnome"]
    session: str = "tty"                          # wayland | x11 | tty
    desktop_session: str = ""
    compositor: str = ""                          # a running wlroots compositor or X11 WM, if any
    distro: str = ""
    distro_like: list = field(default_factory=list)
    which: object = shutil.which

    def has(self, tool):
        return self.which(tool) is not None

    @property
    def pkg(self):
        for d in [self.distro, *self.distro_like]:
            if d in PKG:
                return PKG[d]
        return None

    def packages(self, name):
        names = PACKAGES.get(name, {})
        return names.get(self.pkg) or names.get("*") or []

    @property
    def backend(self):
        """The desktop backend to use: gnome, kde, xfce, cinnamon, mate, lxqt, wlroots, x11wm or generic."""
        d = set(self.desktops)
        if "kde" in d:
            return "kde"
        if "x-cinnamon" in d or "cinnamon" in d:
            return "cinnamon"
        if "xfce" in d:
            return "xfce"
        if "mate" in d:
            return "mate"
        if "lxqt" in d:
            return "lxqt"
        if d & set(WLROOTS) or self.compositor in WLROOTS:
            return "wlroots"
        if "gnome" in d or "budgie" in d or "unity" in d:
            return "gnome"
        if self.session == "x11":
            return "x11wm"
        return "generic"

    def describe(self):
        return (f"desktop {':'.join(self.desktops) or '?'} · session {self.session}"
                + (f" · compositor {self.compositor}" if self.compositor else "")
                + f" · distro {self.distro or '?'}" + (f" ({self.pkg})" if self.pkg else ""))


def parse_os_release(text):
    out = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def running(names):
    """The first of these process names that's running (pgrep -x), or ""."""
    rc, out = run("pgrep", "-u", str(os.getuid()), "-l", "-i", "-x", "|".join(names))
    if rc != 0:
        return ""
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lower() in names:
            return parts[1].lower()
    return ""


def detect(environ=None, os_release=None, compositor=None, which=shutil.which):
    environ = os.environ if environ is None else environ
    desktops = [d.strip().lower() for d in environ.get("XDG_CURRENT_DESKTOP", "").split(":") if d.strip()]
    session = environ.get("XDG_SESSION_TYPE", "").lower()
    if session not in ("wayland", "x11"):
        session = "wayland" if environ.get("WAYLAND_DISPLAY") else "x11" if environ.get("DISPLAY") else "tty"
    if os_release is None:
        try:
            os_release = Path("/etc/os-release").read_text()
        except OSError:
            os_release = ""
    rel = parse_os_release(os_release)
    if compositor is None:
        names = [n.lower() for n in (*WLROOTS, *X11_WMS)]
        compositor = running(names) if not desktops or session == "x11" or set(desktops) & set(WLROOTS) else ""
    return Env(desktops=desktops, session=session, desktop_session=environ.get("DESKTOP_SESSION", ""),
               compositor=compositor.lower(), distro=rel.get("ID", "").lower(),
               distro_like=rel.get("ID_LIKE", "").lower().split(), which=which)
