"""Every desktop backend, driven through the engine with a fake command runner: the right settings
and commands for its desktop, A/B switching, backups that restore, and shortcut hints."""
import unittest
from unittest import mock

from fakes import FakeRun, tools
from helpers import fake_home, make_image

from wallrice import backends, backup, engine, paths
from wallrice.detect import detect
from wallrice.render import terminals

XFCE_DESKTOP = {f"xfconf:xfce4-desktop:/backdrop/screen0/monitorVirtual-1/workspace{w}/last-image": "/usr/share/old.jpg"
                for w in range(2)}


def env_for(desktop, session="x11", compositor="", *have):
    return detect(environ={"XDG_CURRENT_DESKTOP": desktop, "XDG_SESSION_TYPE": session}, os_release="ID=fedora\n",
                  compositor=compositor, which=tools(*have))


class Backends(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.object(backup, "run", lambda *a, **k: (0, "")),
                        mock.patch.object(backup, "has", lambda t: False),
                        mock.patch.object(terminals, "send_osc", lambda th, terminals=None: 0),
                        mock.patch("wallrice.render.icons.papirus_base", lambda: None)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def apply(self, home, env, fake, name="w.png", kind="colour"):
        be = backends.get(env, fake)
        engine.apply(make_image(home / "Pictures/walls/space" / name, kind), effect="none", env=env, backend=be, quiet=True)
        return be

    def test_xfce(self):
        with fake_home() as home:
            fake = FakeRun(dict(XFCE_DESKTOP, **{"xfconf:xsettings:/Net/ThemeName": "Greybird"}))
            env = env_for("XFCE", "x11", "", "xfconf-query", "xfce4-terminal")
            be = self.apply(home, env, fake)
            self.assertEqual(be.name, "xfce")
            v = fake.values
            for w in range(2):
                prop = f"xfconf:xfce4-desktop:/backdrop/screen0/monitorVirtual-1/workspace{w}"
                self.assertTrue(v[f"{prop}/last-image"].endswith("w.png"))
                self.assertEqual(v[f"{prop}/image-style"], "5", "zoomed, like the picker shows it")
            self.assertEqual(v["xfconf:xsettings:/Net/ThemeName"], "Wallrice-a")
            self.assertEqual(len(v["xfconf:xfce4-terminal:/color-palette"].split(";")), 16)
            css = (paths.data_home() / "themes/Wallrice-a/gtk-3.0/gtk.css").read_text()
            self.assertIn("#XfcePanelWindow", css)
            self.apply(home, env, fake, "x.png", "grey")
            self.assertEqual(v["xfconf:xsettings:/Net/ThemeName"], "Wallrice-b")
            backup.restore(say=lambda *a: None, writer=be.restore_setting)
            self.assertEqual(v["xfconf:xsettings:/Net/ThemeName"], "Greybird")
            self.assertEqual(v["xfconf:xfce4-desktop:/backdrop/screen0/monitorVirtual-1/workspace0/last-image"],
                             "/usr/share/old.jpg")
            be.bind_key("<Super>w", "wallrice pick", "wallrice-pick")
            self.assertEqual(v["xfconf:xfce4-keyboard-shortcuts:/commands/custom/<Super>w"], "wallrice pick")
            be.unbind_keys()
            self.assertNotIn("xfconf:xfce4-keyboard-shortcuts:/commands/custom/<Super>w", v)

    def test_kde(self):
        with fake_home() as home:
            fake = FakeRun({"kde:General:ColorScheme": "BreezeDark"})
            env = env_for("KDE", "wayland", "", "dconf", "kreadconfig6", "plasma-apply-colorscheme")
            be = self.apply(home, env, fake)
            self.assertEqual(be.name, "kde")
            self.assertTrue(fake.ran("plasma-apply-wallpaperimage")[0][-1].endswith("w.png"))
            calls = fake.ran("plasma-apply-colorscheme")
            self.assertEqual(calls[0], ["plasma-apply-colorscheme", "Wallrice-a"], "the scheme first")
            self.assertEqual(calls[1][1], "--accent-color", "then the accent on its own call")
            colors = (paths.data_home() / "color-schemes/Wallrice-a.colors").read_text()
            for group in ("Colors:Window", "Colors:View", "Colors:Selection", "Colors:Button", "WM"):
                self.assertIn(f"[{group}]", colors)
            self.assertEqual(fake.values["/org/gnome/desktop/interface/gtk-theme"], "'Wallrice-a'", "GTK apps on Wayland")
            self.apply(home, env, fake, "x.png", "bright")
            self.assertEqual(fake.ran("plasma-apply-colorscheme")[-2][-1], "Wallrice-b", "A/B: Plasma re-applies")
            self.assertIn("Meta+W", be.bind_hint("<Super>w", "wallrice pick"))

    def test_cinnamon_and_mate(self):
        for desktop, bg_key in (("X-Cinnamon", "/org/cinnamon/desktop/background/picture-uri"),
                                ("MATE", "/org/mate/desktop/background/picture-filename")):
            with fake_home() as home:
                fake = FakeRun()
                env = env_for(desktop, "x11", "", "dconf")
                be = self.apply(home, env, fake)
                self.assertIn("w.png", fake.values[bg_key])
                iface = "/org/cinnamon/desktop/interface" if "cinnamon" in bg_key else "/org/mate/desktop/interface"
                self.assertEqual(fake.values[f"{iface}/gtk-theme"], "'Wallrice-a'")
                self.assertEqual(be.current_slot(), "a")
                be.bind_key("<Super>w", "wallrice pick", "wallrice-pick")
                self.assertTrue(any("wallrice-pick" in k for k in fake.values))

    def test_hyprland(self):
        with fake_home() as home:
            fake = FakeRun()
            env = env_for("Hyprland", "wayland", "", "swww", "hyprctl", "dconf", "waybar")
            be = backends.get(env, fake)
            ctx = engine.apply(make_image(home / "Pictures/walls/a.png"), effect="grow", env=env, backend=be, quiet=True)
            swww = fake.ran("swww")[-1]
            self.assertEqual(swww[:2], ["swww", "img"])
            self.assertEqual(swww[swww.index("--transition-type") + 1], "grow")
            self.assertEqual(swww[swww.index("--transition-pos") + 1], "100,200", "grows from the pointer")
            self.assertTrue(any(c[:3] == ["hyprctl", "keyword", "general:col.active_border"] for c in fake.ran("hyprctl")))
            self.assertIn(["pkill", "-SIGUSR2", "-x", "waybar"], fake.ran("pkill"))
            self.assertTrue((paths.config_home() / "hypr/wallrice.conf").is_file())
            self.assertEqual(fake.values["/org/gnome/desktop/interface/gtk-theme"], "'Wallrice-a'")
            self.assertGreater(ctx.settle, 0.5, "the picker waits for swww's animation")
            self.assertIn("bind = SUPER, W, exec, wallrice pick", be.bind_hint("<Super>w", "wallrice pick"))
            self.assertIn("exec-once", be.autostart_hint("wallrice login"))

    def test_sway_with_swaybg(self):
        with fake_home() as home, mock.patch("subprocess.Popen") as popen:
            fake = FakeRun()
            env = env_for("sway", "wayland", "", "swaybg", "swaymsg")
            self.apply(home, env, fake)
            self.assertEqual(popen.call_args[0][0][:3], ["swaybg", "-m", "fill"])
            focused = [c for c in fake.ran("swaymsg") if c[1] == "client.focused"]
            self.assertEqual(len(focused), 1)
            self.assertIn("client.focused", (paths.config_home() / "sway/wallrice").read_text())

    def test_i3(self):
        with fake_home() as home:
            fake = FakeRun()
            env = env_for("", "x11", "i3", "feh", "i3-msg")
            be = self.apply(home, env, fake)
            self.assertEqual(be.name, "x11wm")
            self.assertEqual(fake.ran("feh")[0][:3], ["feh", "--no-fehbg", "--bg-fill"])
            self.assertIn(["i3-msg", "reload"], fake.ran("i3-msg"))
            self.assertIn("client.focused", (paths.config_home() / "i3/wallrice").read_text())
            self.assertIn("bindsym $mod+w exec", be.bind_hint("<Super>w", "wallrice pick"))
            ini = (paths.config_home() / "gtk-3.0/settings.ini").read_text()
            self.assertIn("gtk-theme-name=Wallrice-a", ini)

    def test_lxqt_keeps_other_settings(self):
        with fake_home() as home:
            conf = paths.config_home() / "lxqt/lxqt.conf"
            conf.parent.mkdir(parents=True)
            conf.write_text("[General]\ntheme=frost\n\n[Palette]\nwindow_color=#ffffff\n")
            fake = FakeRun()
            env = env_for("LXQt", "x11", "", "pcmanfm-qt")
            self.apply(home, env, fake)
            self.assertIn("--wallpaper-mode=zoom", fake.ran("pcmanfm-qt")[0])
            text = conf.read_text()
            self.assertIn("theme=frost", text)
            self.assertNotIn("window_color=#ffffff", text)
            self.assertIn("highlight_color=#", text)

    def test_every_desktop_has_a_backend(self):
        for desktop, want in (("GNOME", "gnome"), ("KDE", "kde"), ("XFCE", "xfce"), ("X-Cinnamon", "cinnamon"),
                              ("MATE", "mate"), ("LXQt", "lxqt"), ("Hyprland", "wlroots"), ("sway", "wlroots")):
            self.assertEqual(backends.get(env_for(desktop)).name, want)


class X11Overlay(unittest.TestCase):
    def test_effects_go_from_old_to_new(self):
        try:
            import cairo

            from wallrice.ui import transition_x11 as tx
        except (ImportError, ValueError) as e:
            self.skipTest(f"needs GTK 3 + cairo: {e}")
        w, h = 160, 90

        def solid(rgb):
            s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            cr = cairo.Context(s)
            cr.set_source_rgb(*rgb)
            cr.paint()
            return s

        old, new = solid((1, 0, 0)), solid((0, 0, 1))

        def blue_share(effect, p):
            out = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            cr = cairo.Context(out)
            cr.set_source_surface(old, 0, 0)
            cr.paint()
            if p > 0:
                tx.paint_new(cr, effect, w, h, new, p, (w / 2, h / 2), 0.3)
            data = out.get_data()
            blue = sum(data[i] for i in range(0, len(data), 4))  # BGRA: byte 0 is blue
            return blue / (255 * w * h)

        for effect in tx.EFFECTS:
            self.assertAlmostEqual(blue_share(effect, 0.0), 0.0, places=2, msg=effect)
            self.assertGreater(blue_share(effect, 1.0), 0.97, effect)
            self.assertTrue(0.05 < blue_share(effect, 0.5) < 0.95, effect)


if __name__ == "__main__":
    unittest.main()
