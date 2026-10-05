"""Parts of the theme turned off and on (`wallrice off|on PART…`, `wallrice parts`): saved, respected by
every later wallpaper change, and reversible, with originals restored from the backup."""
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from fakes import FakeRun
from helpers import fake_home, make_image
from test_engine import ORIGINAL, gnome

from wallrice import backup, cli, engine, parts, paths, setup, state
from wallrice.backends import gnome as gnome_backend
from wallrice.render import terminals

IFACE = "/org/gnome/desktop/interface"
DOCK = "/org/gnome/shell/extensions/dash-to-dock"
WITH_DOCK = dict(ORIGINAL, **{f"{IFACE}/gtk-theme": "'Adwaita'", f"{IFACE}/accent-color": "'orange'",
                              f"{DOCK}/background-color": "'rgb(255,120,0)'"})


class Names(unittest.TestCase):
    def test_parts_and_aliases(self):
        self.assertEqual([p.name for p in parts.PARTS], ["apps", "icons", "terminal", "dock", "taskbar-icons",
                                                          "topbar", "transitions", "rotation"])
        self.assertEqual(parts.resolve("taskbar").name, "taskbar-icons")
        self.assertEqual(parts.resolve("App-Icons").name, "taskbar-icons")
        self.assertEqual(parts.resolve("animations").name, "transitions")
        self.assertIsNone(parts.resolve("sparkles"))

    def test_older_settings_still_count(self):
        """terminal_colors, dock_mono and animations (from earlier versions) are the same parts."""
        on = parts.enabled({"terminal_colors": False, "dock_mono": False, "animations": False})
        self.assertFalse(on["terminal"])
        self.assertFalse(on["taskbar-icons"])
        self.assertFalse(on["transitions"])
        self.assertTrue(on["apps"])


class OnOff(unittest.TestCase):
    def setUp(self):
        self.sent, self.resets, self.rotation = [], [], []
        self.patches = [mock.patch.object(backup, "run", lambda *a, **k: (0, "")),
                        mock.patch.object(backup, "has", lambda t: False),
                        mock.patch.object(terminals, "send_osc", lambda th, terminals=None: self.sent.append(1)),
                        mock.patch.object(terminals, "send_reset", lambda terminals=None: self.resets.append(1)),
                        mock.patch.object(setup, "set_rotation", lambda m, *a, **k: self.rotation.append(m)),
                        mock.patch("wallrice.render.icons.papirus_base", lambda: None),
                        mock.patch.object(gnome_backend.Gnome, "dock_installed", lambda self: True)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_apps_off_puts_the_originals_back_and_stays_off(self):
        with fake_home() as home:
            mine = home / ".config/gtk-4.0/gtk.css"
            mine.parent.mkdir(parents=True)
            mine.write_text("/* my own tweaks */\n")
            fake = FakeRun(WITH_DOCK)
            env, be = gnome(fake)
            engine.apply(make_image(home / "a.png"), effect="none", env=env, backend=be, quiet=True)
            self.assertEqual(fake.values[f"{IFACE}/gtk-theme"], "'Wallrice-a'")

            engine.part_off(["apps"], env=env, backend=be)
            self.assertEqual(fake.values[f"{IFACE}/gtk-theme"], "'Adwaita'")
            self.assertEqual(fake.values[f"{IFACE}/accent-color"], "'orange'")
            self.assertEqual(mine.read_text(), "/* my own tweaks */\n", "the user's own gtk.css is back")

            engine.apply(make_image(home / "b.png", "bright"), effect="none", env=env, backend=be, quiet=True)
            self.assertEqual(fake.values[f"{IFACE}/gtk-theme"], "'Adwaita'", "later wallpapers leave apps alone")
            self.assertEqual(mine.read_text(), "/* my own tweaks */\n")
            self.assertTrue(fake.values[f"{DOCK}/background-color"].startswith("'#"), "the dock still follows")

            engine.part_on(["apps"], env=env, backend=be)
            self.assertTrue(fake.values[f"{IFACE}/gtk-theme"].startswith("'Wallrice-"), "on again: right away")

    def test_dock_and_taskbar_icons(self):
        with fake_home() as home:
            fake = FakeRun(WITH_DOCK)
            env, be = gnome(fake)
            engine.apply(make_image(home / "a.png"), effect="none", env=env, backend=be, quiet=True)
            engine.part_off(["dock", "taskbar-icons"], env=env, backend=be)
            self.assertEqual(fake.values[f"{DOCK}/background-color"], "'rgb(255,120,0)'")
            settings = json.loads((paths.data() / "gnome-shell.json").read_text())
            self.assertEqual((settings["dock"], settings["dock_mono"], settings["topbar"]), (False, False, True),
                             "the extension restyles the real dock at once")
            engine.apply(make_image(home / "b.png", "grey"), effect="none", env=env, backend=be, quiet=True)
            self.assertEqual(fake.values[f"{DOCK}/background-color"], "'rgb(255,120,0)'")

    def test_everything_off_then_on(self):
        with fake_home() as home:
            fake = FakeRun(WITH_DOCK)
            env, be = gnome(fake)
            engine.apply(make_image(home / "a.png"), effect="none", env=env, backend=be, quiet=True)
            engine.part_off([p.name for p in parts.PARTS], env=env, backend=be)
            v = fake.values
            self.assertEqual(v[f"{IFACE}/gtk-theme"], "'Adwaita'")
            self.assertEqual(v["/org/gnome/Ptyxis/Profiles/df8d/palette"], "'Monokai Dark'")
            self.assertEqual(v[f"{DOCK}/background-color"], "'rgb(255,120,0)'")
            self.assertEqual(self.resets, [1])
            self.assertEqual(self.rotation, [0], "the timer stops")
            settings = json.loads((paths.data() / "gnome-shell.json").read_text())
            self.assertFalse(settings["topbar"])
            self.assertTrue(all(not on for on in parts.enabled(state.load_state()).values()))

            sent = len(self.sent)
            ctx = engine.apply(make_image(home / "b.png"), effect="grow", env=env, backend=be, quiet=True)
            self.assertEqual(ctx.effect, "none", "transitions off")
            self.assertIn("b.png", v["/org/gnome/desktop/background/picture-uri"], "the wallpaper itself still changes")
            self.assertEqual(v[f"{IFACE}/gtk-theme"], "'Adwaita'")
            self.assertEqual(len(self.sent), sent)

            engine.part_on([p.name for p in parts.PARTS], env=env, backend=be)
            self.assertTrue(v[f"{IFACE}/gtk-theme"].startswith("'Wallrice-"))
            self.assertTrue(v["/org/gnome/Ptyxis/Profiles/df8d/palette"].startswith("'wallrice-"))
            self.assertEqual(self.rotation, [0, 30], "the timer starts again")
            self.assertTrue(json.loads((paths.data() / "gnome-shell.json").read_text())["topbar"])


class CommandLine(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out), mock.patch("sys.stderr", io.StringIO()):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_on_off_parts(self):
        with fake_home(), mock.patch.object(engine, "part_off", return_value=2) as off, \
                mock.patch.object(engine, "part_on", return_value=[]) as on:
            self.assertEqual(self.run_cli("off", "taskbar", "terminal")[0], 0)
            self.assertEqual(off.call_args[0][0], ["taskbar-icons", "terminal"])
            self.assertEqual(self.run_cli("on", "all")[0], 0)
            self.assertEqual(on.call_args[0][0], [p.name for p in parts.PARTS])
            self.assertEqual(self.run_cli("off", "sparkles")[0], 2)
            self.assertEqual(self.run_cli("off")[0], 2, "nothing named: nothing turned off")
            self.assertEqual(self.run_cli("bar", "colour")[0], 0)
            self.assertEqual(off.call_args[0][0], ["taskbar-icons"], "the older shortcut")

    def test_parts_listing(self):
        with fake_home(), mock.patch("wallrice.detect.detect") as det:
            det.return_value = mock.Mock(backend="gnome", has=lambda t: False)
            state.update_state(terminal_colors=False)
            code, out = self.run_cli("parts")
            self.assertEqual(code, 0)
            self.assertIn("off  terminal", out)
            self.assertIn("on   taskbar-icons", out)


class OtherDesktops(unittest.TestCase):
    def test_xfce_apps_off(self):
        from test_backends import XFCE_DESKTOP, env_for
        from wallrice import backends
        with fake_home() as home, mock.patch.object(backup, "run", lambda *a, **k: (0, "")), \
                mock.patch.object(terminals, "send_osc", lambda th, terminals=None: 0), \
                mock.patch("wallrice.render.icons.papirus_base", lambda: None):
            fake = FakeRun(dict(XFCE_DESKTOP, **{"xfconf:xsettings:/Net/ThemeName": "Greybird"}))
            env = env_for("XFCE", "x11", "", "xfconf-query", "xfce4-terminal")
            be = backends.get(env, fake)
            state.update_state(apps=False)
            engine.apply(make_image(home / "a.png"), effect="none", env=env, backend=be, quiet=True)
            self.assertEqual(fake.values["xfconf:xsettings:/Net/ThemeName"], "Greybird")
            self.assertFalse((paths.data_home() / "themes/Wallrice-a").exists(), "no theme files while off")
            self.assertTrue(any(k.startswith("xfconf:xfce4-terminal:") for k in fake.values), "terminal still on")


if __name__ == "__main__":
    unittest.main()
