"""Readable colours from any wallpaper: derive() on dark, bright and grey palettes, and on real images
through the built-in (Pillow) extractor."""
import unittest
from unittest import mock

from helpers import BRIGHT, DARK, GREY, fake_home, make_image

from wallrice import palette, theme
from wallrice.color import contrast, hls, luminance


class Derive(unittest.TestCase):
    def check(self, pal):
        c = theme.derive(pal)
        self.assertLessEqual(luminance(c["bg"]), 0.03, "background must be dark")
        self.assertGreaterEqual(contrast(c["fg"], c["bg"]), 7.0, "text must be readable (7:1)")
        self.assertGreaterEqual(contrast(c["accent"], c["bg"]), 3.0, "accent must stand out (3:1)")
        self.assertGreaterEqual(contrast(c["on_accent"], c["accent"]), 3.0, "text on accent readable")
        self.assertGreaterEqual(contrast(c["muted"], c["bg"]), 4.5)
        for i, t in enumerate(c["term"]):
            if i not in (0, 8):
                self.assertGreaterEqual(contrast(t, c["bg"]), 4.5, f"terminal colour {i}")
        return c

    def test_bright_wallpaper(self):
        self.check(BRIGHT)

    def test_dark_wallpaper(self):
        self.check(DARK)

    def test_grey_wallpaper_gets_violet(self):
        c = self.check(GREY)
        h, _l, s = hls(c["accent"])
        self.assertGreaterEqual(s, 0.25, "a grey wallpaper still gets an accent with some colour")
        self.assertTrue(0.68 < h < 0.78, f"no hue to keep, so the accent is violet, not red (hue {h:.2f})")

    def test_dark_accent_keeps_its_colour(self):
        """A dark, saturated brown becomes a lighter brown, not a washed-out grey."""
        from helpers import palette as pal
        c = theme.derive(pal("#120a06", "#e0d8d0", ["#120a06", "#3a2516", "#2e2420", "#332820", "#2a221e", "#30261f", "#28201b", "#d0c8c0"] * 2))
        _h, l, s = hls(c["accent"])
        self.assertGreater(s, 0.3, "still clearly coloured")
        self.assertGreaterEqual(l, 0.45)
        self.assertGreaterEqual(contrast(c["accent"], c["bg"]), 3.0)

    def test_text_is_near_white_not_neon(self):
        """A saturated foreground (an ocean picture's light cyan) still gives calm, near-white text."""
        from helpers import palette as pal
        c = theme.derive(pal("#081554", "#52f4fe", ["#081554", "#2d98b2", "#52f4fe", "#1b6ca8", "#3fa7d6", "#0e4d92", "#81e8ff", "#c8f8ff"] * 2))
        _h, l, s = hls(c["fg"])
        self.assertLessEqual(s, 0.31)
        self.assertGreaterEqual(l, 0.8)
        self.assertGreaterEqual(contrast(c["fg"], c["bg"]), 7.0)

    def test_grey_wallpaper_terminal_still_has_colours(self):
        """Grey slots become ANSI-like colours, so errors and successes still look different."""
        c = theme.derive(GREY)
        hues = [hls(c["term"][i])[0] for i in range(1, 7)]
        for i in range(1, 7):
            self.assertGreater(hls(c["term"][i])[2], 0.25, f"terminal colour {i} isn't grey")
        self.assertGreater(max(hues) - min(hues), 0.3, "several different hues")
        self.assertTrue(0.68 < hls(c["accent"])[0] < 0.78, "the accent is still violet")

    def test_colourful_terminal_left_alone(self):
        """A colourful wallpaper's terminal colours are its own (only raised to 4.5:1)."""
        from wallrice.color import WHITE, hex2rgb, rgb2hex, toward
        c = theme.derive(DARK)
        for i in range(1, 7):
            want = toward(hex2rgb(DARK[f"color{i}"]), WHITE, c["bg"], 4.5)
            self.assertEqual(rgb2hex(c["term"][i]), rgb2hex(want))

    def test_nearest_named_accent(self):
        named = {"blue": "#3584e4", "red": "#e62d42", "purple": "#9141ac", "slate": "#6f8396"}
        self.assertEqual(theme.nearest(theme.BRAND, named), "purple")
        self.assertEqual(theme.nearest((0.2, 0.5, 0.9), named), "blue")
        self.assertEqual(theme.nearest((0.45, 0.48, 0.5), named), "slate")

    def test_mix_theme_endpoints(self):
        a, b = theme.derive(DARK), theme.derive(BRIGHT)
        self.assertEqual(theme.hexes(theme.mix_theme(a, b, 0)), theme.hexes(a))
        self.assertEqual(theme.hexes(theme.mix_theme(a, b, 1)), theme.hexes(b))


class BuiltinExtractor(unittest.TestCase):
    """Without wallust (most distros), Pillow makes the palette; derive() keeps it readable."""

    def test_images(self):
        with fake_home() as home:
            for kind in ("colour", "bright", "grey"):
                img = make_image(home / f"{kind}.png", kind)
                pal = palette.extract(img, use_wallust=False)
                self.assertEqual(len([k for k in pal if k.startswith("color")]), 16)
                self.assertEqual(pal["background"], pal["color0"])
                c = Derive.check(self, pal)
                if kind == "grey":
                    self.assertTrue(0.68 < hls(c["accent"])[0] < 0.78, "grey picture: violet accent")
                if kind == "colour":
                    self.assertGreater(hls(c["accent"])[2], 0.4, "a colourful picture gives a colourful accent")

    def test_cache_means_one_extraction(self):
        with fake_home() as home:
            img = make_image(home / "a.png")
            with mock.patch.object(palette, "pillow_palette", wraps=palette.pillow_palette) as pp:
                p1 = palette.extract(img, use_wallust=False)
                p2 = palette.extract(img, use_wallust=False)
            self.assertEqual(p1, p2)
            self.assertEqual(pp.call_count, 1)
            self.assertTrue(str(palette.cache_path(img)).startswith(str(home / ".cache" / "wallrice")))


class Wallust(unittest.TestCase):
    def test_printout_parsed_and_own_cache_off(self):
        """The 16 colours come from wallust's printout (its info line ignored), with wallust's own
        cache off (it grows by megabytes per image)."""
        hexes = [f"#{i:02x}{i:02x}{i + 5:02x}" for i in range(0, 160, 10)]
        out = "\x1b[1m[I]\x1b[0m config: Not using a configuration file.\n" + "\n".join(hexes) + "\n"
        run = mock.Mock(return_value=mock.Mock(returncode=0, stdout=out, stderr=""))
        with fake_home() as home, mock.patch.object(palette.subprocess, "run", run):
            img = home / "w.jpg"
            img.write_bytes(b"not read: wallust is mocked")
            p = palette.extract(img, use_wallust=True)
            self.assertEqual([p[f"color{i}"] for i in range(16)], hexes)
            self.assertEqual((p["background"], p["foreground"]), (hexes[0], hexes[15]))
            args = run.call_args[0][0]
            self.assertIn("-n", args)
            self.assertIn("--print-scheme", args)

    def test_failure_falls_back_to_pillow(self):
        run = mock.Mock(return_value=mock.Mock(returncode=1, stdout="", stderr="boom"))
        with fake_home() as home, mock.patch.object(palette.subprocess, "run", run):
            img = make_image(home / "a.png")
            p = palette.extract(img, use_wallust=True)
            self.assertEqual(len(p), 19)


if __name__ == "__main__":
    unittest.main()
