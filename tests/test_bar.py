"""Top bar styles: one definition per style drives both the GNOME Shell stylesheet and the previews;
choosing a style rewrites the extension's files (which it reloads live); the chooser draws offscreen."""
import json
import unittest
from unittest import mock

from helpers import DARK, fake_home, make_image

from wallrice import barstyles, cli, paths
from wallrice.backends import gnome
from wallrice.state import load_state, update_state
from wallrice.theme import derive

try:
    from wallrice.ui import barchooser, common
except (ImportError, ValueError) as e:
    barchooser = common = None
    SKIP = str(e)
else:
    SKIP = ""


class Styles(unittest.TestCase):
    def test_nine_styles_by_number_or_id(self):
        self.assertEqual(len(barstyles.STYLES), 9)
        self.assertEqual(barstyles.get("4").id, "pills")
        self.assertEqual(barstyles.get("glass").name, "Glass")
        self.assertEqual(barstyles.get("nonsense").id, barstyles.DEFAULT)
        self.assertEqual(barstyles.get(None).id, barstyles.DEFAULT)

    def test_css_is_scoped_and_differs_per_style(self):
        th = derive(DARK)
        sheets = {s.id: barstyles.shell_css(th, s) for s in barstyles.STYLES}
        self.assertEqual(len(set(sheets.values())), 9, "every style looks different")
        for css in sheets.values():
            for line in css.splitlines():
                if "{" in line and not line.startswith("/*"):
                    selector = line.split("{")[0]
                    self.assertTrue(any(k in selector for k in ("wallrice", "dashtodockContainer.wallrice-dock")),
                                    f"unscoped rule: {line[:80]}")
        self.assertIn("border-left", sheets["sidebars"])
        self.assertIn("border-bottom", sheets["underline"])
        self.assertIn("box-shadow: 0 0 6px", sheets["glow"])
        self.assertIn("wallrice-clock", sheets["filled"])
        self.assertNotIn("wallrice-clock {", sheets["outlined"])

    def test_choosing_a_style_rewrites_the_extension_files(self):
        with fake_home() as home:
            img = make_image(home / "Pictures/walls/space/a.png")
            update_state(wallpaper=str(img))
            code = cli.main(["bar", "pills"])
            self.assertEqual(code, 0)
            self.assertEqual(load_state()["bar_style"], "pills")
            settings = json.loads((paths.data() / "gnome-shell.json").read_text())
            self.assertEqual(settings["bar_style"], "pills")
            self.assertIn("(pills)", gnome.shell_css_path().read_text())
            cli.main(["bar", "colour"])
            self.assertFalse(json.loads((paths.data() / "gnome-shell.json").read_text())["dock_mono"])

    def test_unknown_style_is_an_error(self):
        if barchooser is None:
            self.skipTest(SKIP)
        with fake_home(), mock.patch("builtins.print"):
            self.assertEqual(barchooser.set_style("sparkly"), 2)


@unittest.skipIf(barchooser is None, f"needs GTK 3 + cairo: {SKIP}")
class Chooser(unittest.TestCase):
    def test_draws_and_moves(self):
        with fake_home() as home:
            img = make_image(home / "Pictures/walls/space/a.png")
            update_state(wallpaper=str(img), bar_style="glass")
            v = barchooser.ChooserView(now=0.0)
            self.assertEqual(v.style.id, "glass")
            self.assertTrue(v.select(v.sel + 1, now=0.0))
            self.assertFalse(v.select(v.sel, now=0.1))
            common.save_png(lambda cr: v.draw(cr, 0.5), barchooser.W, barchooser.H, home / "c.png")
            self.assertEqual(len(v.rows), 9)
            self.assertEqual(v.row_at(*[c + 5 for c in v.rows[2][:2]]), 2)

    def test_preview_matches_every_style(self):
        import cairo
        th = derive(DARK)
        for s in barstyles.STYLES:
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1920, 48)
            h = barstyles.draw_bar(cairo.Context(surf), th, s, 1920, text=common.text)
            self.assertGreater(h, 30)


class Extension(unittest.TestCase):
    def test_metadata(self):
        meta = json.loads((paths.resource("gnome-extension", "wallrice@teterw.github.io", "metadata.json")).read_text())
        self.assertEqual(meta["uuid"], "wallrice@teterw.github.io")
        self.assertIn("50", meta["shell-version"])

    def test_gnome_backend_writes_shell_files(self):
        with fake_home():
            files = gnome.shell_files(derive(DARK))
            self.assertEqual({p.name for p in files}, {"gnome-shell.css", "gnome-shell.json"})


if __name__ == "__main__":
    unittest.main()
