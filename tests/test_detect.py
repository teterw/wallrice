"""Desktop detection with faked environments: every common desktop maps to the right backend."""
import unittest

import helpers  # noqa: F401  (puts the repo on sys.path)

from wallrice.detect import detect

FEDORA = 'NAME="Fedora Linux"\nID=fedora\nVERSION_ID=44\n'
UBUNTU = "ID=ubuntu\nID_LIKE=debian\n"
MINT = "ID=linuxmint\nID_LIKE=\"ubuntu debian\"\n"
ARCH = "ID=arch\n"
TUMBLEWEED = 'ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n'


def env(desktop, session="wayland", rel=FEDORA, compositor="", **extra):
    e = {"XDG_CURRENT_DESKTOP": desktop, "XDG_SESSION_TYPE": session, **extra}
    return detect(environ=e, os_release=rel, compositor=compositor, which=lambda t: None)


class Backends(unittest.TestCase):
    def test_desktops(self):
        cases = [
            (env("GNOME"), "gnome"),
            (env("ubuntu:GNOME", rel=UBUNTU), "gnome"),
            (env("Budgie:GNOME"), "gnome"),
            (env("KDE", rel=ARCH), "kde"),
            (env("XFCE", "x11", MINT), "xfce"),
            (env("X-Cinnamon", "x11", MINT), "cinnamon"),
            (env("MATE", "x11"), "mate"),
            (env("LXQt"), "lxqt"),
            (env("Hyprland", rel=ARCH), "wlroots"),
            (env("sway"), "wlroots"),
            (env("", "wayland", compositor="niri"), "wlroots"),
            (env("", "x11", compositor="i3"), "x11wm"),
            (env("", "tty"), "generic"),
        ]
        for e, want in cases:
            self.assertEqual(e.backend, want, e.describe())

    def test_session_guessed_from_display_variables(self):
        e = detect(environ={"WAYLAND_DISPLAY": "wayland-0"}, os_release="", compositor="", which=lambda t: None)
        self.assertEqual(e.session, "wayland")
        e = detect(environ={"DISPLAY": ":0"}, os_release="", compositor="", which=lambda t: None)
        self.assertEqual(e.session, "x11")

    def test_package_manager(self):
        self.assertEqual(env("GNOME").pkg, "dnf")
        self.assertEqual(env("X-Cinnamon", rel=MINT).pkg, "apt")
        self.assertEqual(env("KDE", rel=ARCH).pkg, "pacman")
        self.assertEqual(env("KDE", rel=TUMBLEWEED).pkg, "zypper")
        self.assertEqual(env("GNOME").packages("pygobject"), ["python3-gobject"])
        self.assertEqual(env("GNOME", rel=MINT).packages("pygobject"), ["python3-gi", "python3-gi-cairo", "gir1.2-gtk-3.0"])
        self.assertEqual(env("KDE", rel=ARCH).packages("papirus"), ["papirus-icon-theme"])


if __name__ == "__main__":
    unittest.main()
