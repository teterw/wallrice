"""The review: one press is one choice (auto-repeat never decides), every choice saved at once, undo,
removed pictures leave the disk and stay out, and the drawing works offscreen."""
import json
import unittest
from unittest import mock

from helpers import fake_home, make_image

try:
    from wallrice.ui import common, review
except (ImportError, ValueError) as e:  # no GTK 3 / cairo on this machine
    review = common = None
    SKIP = str(e)
else:
    SKIP = ""

from wallrice import collections, engine, paths
from wallrice.state import load_review, save_review, update_state


@unittest.skipIf(common is None, f"needs GTK 3 + cairo: {SKIP}")
class Guard(unittest.TestCase):
    def test_auto_repeat_never_acts(self):
        g = common.KeyGuard()
        self.assertTrue(g.press("Left", 1000))
        for t in range(1030, 1700, 30):  # the key is held: repeats every 30 ms
            self.assertFalse(g.press("Left", t))
        g.release("Left")
        self.assertTrue(g.press("Left", 1750))

    def test_late_release_repeat_ignored(self):
        """A busy X server delivered the release late and repeated the key by itself."""
        g = common.KeyGuard()
        self.assertTrue(g.press("Left", 0))
        self.assertFalse(g.press("Left", 650))
        self.assertTrue(g.press("Left", 650 + 700), "a real second press, much later, counts")

    def test_actions_apart(self):
        g = common.KeyGuard(gap=0.2)
        self.assertTrue(g.act(10.0))
        self.assertFalse(g.act(10.1), "a double-click is one choice")
        self.assertTrue(g.act(10.25))


@unittest.skipIf(review is None, f"needs GTK 3 + cairo: {SKIP}")
class Review(unittest.TestCase):
    def view(self, home, n=3):
        for i in range(n):
            make_image(home / f"Pictures/walls/space/p{i}.png", ("colour", "bright", "grey")[i % 3])
        return review.ReviewView(960, 540)

    def test_choices_saved_at_once_and_undo(self):
        with fake_home() as home:
            v = self.view(home)
            self.assertEqual(len(v.queue), 3)
            self.assertTrue(v.decide("keep", now=1.0))
            self.assertEqual(load_review()["keep"], {"space/p0.png"})
            self.assertFalse(v.decide("remove", now=1.1), "too soon: a double-click counts once")
            self.assertTrue(v.decide("remove", now=1.5))
            self.assertEqual(load_review()["drop"], {"space/p1.png"})
            self.assertTrue(v.undo(now=2.0))
            self.assertEqual(load_review()["drop"], set())
            self.assertEqual(v.i, 1)
            self.assertTrue(v.undo(now=2.5))
            self.assertEqual(load_review()["keep"], set())

    def test_resumes_where_it_stopped(self):
        with fake_home() as home:
            v = self.view(home)
            v.decide("keep", now=1.0)
            v2 = review.ReviewView(960, 540)
            self.assertEqual([collections.rel(p) for p in v2.queue], ["space/p1.png", "space/p2.png"])
            self.assertEqual(v2.before, 1)

    def test_draws_offscreen(self):
        with fake_home() as home:
            v = self.view(home)
            for j in v.wanted():
                v.loaded(j, *v.load(j), now=0.0)
            v.decide("remove", now=1.0)
            for t in (1.1, 1.3, 2.0):
                common.save_png(lambda cr, t=t: v.draw(cr, t), 960, 540, home / f"f{t}.png")
            self.assertTrue((home / "f1.3.png").stat().st_size > 1000)

    def test_finish_removes_files_and_moves_off_current(self):
        with fake_home() as home:
            v = self.view(home)
            cur = v.queue[0]
            update_state(wallpaper=str(cur))
            with mock.patch.object(collections, "sources", return_value={"space": {"list": "space-walls.txt"}}):
                v.decide("remove", now=1.0)
                with mock.patch.object(engine, "apply") as apply:
                    review.finish_work()
                self.assertFalse(cur.exists(), "removed pictures leave the disk")
                apply.assert_called_once()
                self.assertNotEqual(apply.call_args[0][0], cur)
                self.assertNotIn(cur, collections.all_pictures())


class RemovedStayGone(unittest.TestCase):
    def test_review_drops_are_sparse_exclusions(self):
        pats = collections.sparse_patterns({"paths": "/*/ !/.github/"}, {"x/[1] y.jpg", "anime/a*b.png"}).splitlines()
        self.assertEqual(pats[:2], ["/*/", "!/.github/"])
        self.assertIn("!/anime/a\\*b.png", pats)
        self.assertIn("!/x/\\[1] y.jpg", pats)
        self.assertIn("!*.mp4", pats, "no videos")

    def test_dropped_never_listed(self):
        with fake_home() as home:
            for rel in ("space/a.jpg", "elementary/backgrounds/b.jpg", "rose-pine/anime/d.png", "mine/f.webp",
                        "d3ext/.git/objects/x.jpg", "d3ext/images/e.gif"):
                (home / "Pictures/walls" / rel).parent.mkdir(parents=True, exist_ok=True)
                (home / "Pictures/walls" / rel).write_bytes(b"x")
            save_review({"keep": set(), "drop": {"rose-pine/anime/d.png"}})
            got = [collections.rel(p) for p in collections.all_pictures()]
            self.assertEqual(got, ["space/a.jpg", "elementary/backgrounds/b.jpg", "mine/f.webp"])
            calm = [collections.rel(p) for p in collections.wallpapers("calm")]
            self.assertEqual(calm, ["space/a.jpg", "elementary/backgrounds/b.jpg"])
            self.assertEqual(json.loads(paths.review_file().read_text())["drop"], ["rose-pine/anime/d.png"])

    def test_space_list_is_pinned(self):
        entries = collections.list_entries("space-walls.txt")
        self.assertGreater(len(entries), 50)
        self.assertEqual(len({e[2] for e in entries}), len(entries), "file names are unique")
        for sha, url, name, title, credit in entries:
            self.assertRegex(sha, r"^[0-9a-f]{64}$")
            self.assertTrue(url.startswith("https://"), url)
            self.assertTrue(name.endswith(".jpg") and title and credit, name)

    def test_checksum_mismatch_skipped(self):
        with fake_home():
            src = {"list": "space-walls.txt"}
            entries = collections.list_entries("space-walls.txt")[:2]
            good = b"good bytes"
            import hashlib
            fixed = [(hashlib.sha256(good).hexdigest(), "https://x/1.jpg", "one.jpg", "One", "c"),
                     (entries[1][0], "https://x/2.jpg", "two.jpg", "Two", "c")]
            with mock.patch.object(collections, "list_entries", return_value=fixed):
                collections.sync_list("space", src, set(), say=lambda *a: None, fetch=lambda url: good)
            names = sorted(p.name for p in (paths.walls() / "space").iterdir())
            self.assertEqual(names, ["one.jpg"], "a file whose checksum doesn't match is skipped, not installed")


if __name__ == "__main__":
    unittest.main()
