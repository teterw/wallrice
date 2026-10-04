"""The engine and the GNOME backend: A/B themes, one dconf transaction per step, never half-themed,
backups that uninstall can restore, Super+W next to the user's own shortcuts."""
import json
import unittest
from unittest import mock

from fakes import FakeRun, tools
from helpers import fake_home, make_image

from wallrice import backup, engine, paths, state
from wallrice.backends.gnome import ACCENTS, Gnome
from wallrice.detect import detect
from wallrice.render import gtk, terminals

GNOME_ENV = {"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}
ORIGINAL = {"/org/gnome/desktop/interface/gtk-theme": "'Adwaita'",
            "/org/gnome/desktop/interface/accent-color": "'orange'",
            "/org/gnome/Ptyxis/profile-uuids": "['df8d']",
            "/org/gnome/Ptyxis/Profiles/df8d/palette": "'Monokai Dark'",
            "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings":
                "['/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/ptyxis-opacity/']"}


def gnome(fake):
    env = detect(environ=GNOME_ENV, os_release="ID=fedora\n", compositor="", which=tools("dconf", "ptyxis"))
    return env, Gnome(env, run=fake)


class Apply(unittest.TestCase):
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

    def test_gnome_apply_alternates_slots(self):
        with fake_home() as home:
            fake = FakeRun(ORIGINAL)
            env, be = gnome(fake)
            img = make_image(home / "Pictures/walls/space/a b.png")
            engine.apply(img, effect="none", env=env, backend=be, quiet=True)
            v = fake.values
            self.assertEqual(v["/org/gnome/desktop/interface/gtk-theme"], "'Wallrice-a'")
            self.assertEqual(v["/org/gnome/desktop/background/picture-uri"], f"'{img.as_uri()}'")
            self.assertIn("%20", v["/org/gnome/desktop/background/picture-uri-dark"], "spaces are URI-encoded")
            self.assertEqual(v["/org/gnome/desktop/background/picture-options"], "'zoom'")
            self.assertIn(v["/org/gnome/desktop/interface/accent-color"].strip("'"), ACCENTS)
            self.assertEqual(v["/org/gnome/Ptyxis/Profiles/df8d/palette"], "'wallrice-a'")
            self.assertTrue((paths.data_home() / "themes/Wallrice-a/gtk-3.0/gtk.css").is_file())
            self.assertTrue((paths.data_home() / "org.gnome.Ptyxis/palettes/wallrice-a.palette").is_file())
            css = (home / ".config/gtk-4.0/gtk.css").read_text()
            self.assertIn("--window-bg-color", css)
            self.assertIn("@define-color accent_bg_color", css)
            self.assertEqual(state.load_state()["slot"], "a")
            # the wallpaper goes in one transaction, the theme in another
            self.assertEqual(len(fake.loads()), 2)

            engine.apply(make_image(home / "Pictures/walls/b.png", "bright"), effect="none", env=env, backend=be, quiet=True)
            self.assertEqual(v["/org/gnome/desktop/interface/gtk-theme"], "'Wallrice-b'")
            self.assertEqual(v["/org/gnome/Ptyxis/Profiles/df8d/palette"], "'wallrice-b'")
            current = json.loads((paths.cache() / "current.json").read_text())
            self.assertEqual(len(current["term"]), 16)

    def test_failure_keeps_old_theme(self):
        """If any part of a new theme can't be made, nothing is written and nothing is switched."""
        with fake_home() as home:
            fake = FakeRun(ORIGINAL)
            env, be = gnome(fake)
            img = make_image(home / "w.png")
            with mock.patch.object(terminals, "outputs", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    engine.apply(img, effect="none", env=env, backend=be, quiet=True)
            written = [p for p in home.rglob("*") if p.is_file() and p != img and "palettes" not in p.parts]
            self.assertEqual(written, [])
            self.assertEqual(fake.loads(), [])
            self.assertEqual(fake.values, ORIGINAL)

    def test_live_step_failure_doesnt_stop_the_rest(self):
        with fake_home() as home:
            fake = FakeRun(ORIGINAL)
            env, be = gnome(fake)
            sent = []
            with mock.patch.object(be, "activate", return_value=[("broken", mock.Mock(side_effect=OSError("x")))]), \
                    mock.patch.object(terminals, "send_osc", lambda th, terminals=None: sent.append(1)):
                ctx = engine.apply(make_image(home / "w.png"), effect="none", env=env, backend=be, quiet=True)
            self.assertEqual(sent, [1])
            self.assertTrue(any("broken" in n for n in ctx.notes))

    def test_backup_and_restore(self):
        with fake_home() as home:
            fake = FakeRun(ORIGINAL)
            env, be = gnome(fake)
            mine = home / ".config/gtk-4.0/gtk.css"
            mine.parent.mkdir(parents=True)
            mine.write_text("/* my own tweaks */\n")
            engine.apply(make_image(home / "w.png"), effect="none", env=env, backend=be, quiet=True)
            engine.apply(make_image(home / "x.png", "grey"), effect="none", env=env, backend=be, quiet=True)
            self.assertNotIn("my own tweaks", mine.read_text())
            m = backup.load()
            self.assertEqual(m["dconf"]["/org/gnome/desktop/interface/gtk-theme"], "'Adwaita'", "first original kept")
            with mock.patch.object(backup, "run", fake):
                backup.restore(say=lambda *a: None)
            self.assertEqual(fake.values["/org/gnome/desktop/interface/gtk-theme"], "'Adwaita'")
            self.assertEqual(fake.values["/org/gnome/Ptyxis/Profiles/df8d/palette"], "'Monokai Dark'")
            self.assertNotIn("/org/gnome/desktop/background/picture-uri", fake.values, "unset before: unset again")
            self.assertEqual(mine.read_text(), "/* my own tweaks */\n")

    def test_not_an_image(self):
        with fake_home() as home:
            (home / "notes.txt").write_text("hi")
            with self.assertRaises(engine.ApplyError):
                engine.apply(home / "notes.txt", quiet=True)


class Keys(unittest.TestCase):
    def test_super_w_keeps_other_shortcuts(self):
        fake = FakeRun(ORIGINAL)
        _env, be = gnome(fake)
        be.bind_key("<Super>w", "wallrice pick", "wallrice-pick")
        be.bind_key("<Super>w", "wallrice pick", "wallrice-pick")  # twice: still one entry
        lst = fake.values["/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"]
        self.assertEqual(lst.count("wallrice-pick"), 1)
        self.assertIn("ptyxis-opacity", lst)
        base = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/wallrice-pick/"
        self.assertEqual(fake.values[base + "binding"], "'<Super>w'")
        be.unbind_keys()
        lst = fake.values["/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"]
        self.assertNotIn("wallrice", lst)
        self.assertIn("ptyxis-opacity", lst)
        self.assertNotIn(base + "binding", fake.values)


class Terminals(unittest.TestCase):
    def test_escape_sequences_reach_open_terminals(self):
        from helpers import DARK
        from wallrice.theme import derive
        with fake_home() as home:
            tty = home / "pts1"
            tty.write_text("")
            n = terminals.send_osc(derive(DARK), terminals=[tty, home / "missing"])
            self.assertEqual(n, 1)
            seq = tty.read_text()
            self.assertEqual(seq.count("\033]4;"), 16)
            self.assertIn("\033]11;", seq)

    def test_gtk_theme_has_both_variants(self):
        from helpers import DARK
        from wallrice.theme import derive
        with fake_home():
            files = gtk.gtk3_theme(derive(DARK), "b")
            names = {str(p.relative_to(paths.data_home() / "themes")) for p in files}
            self.assertIn("Wallrice-b/gtk-3.0/gtk.css", names)
            self.assertIn("Wallrice-b/gtk-3.0/gtk-dark.css", names)
            self.assertIn("Wallrice-b/index.theme", names)
            css = next(t for p, t in files.items() if p.name == "gtk.css" and "gtk-3.0" in str(p))
            self.assertIn("@import", css, "always builds on a complete theme")


if __name__ == "__main__":
    unittest.main()
