"""The picker's logic: Delete is a review Remove that Ctrl+Z restores exactly, Esc after removing the
current wallpaper applies the one on show, loading goes by priority, search, and the confirm only
closes once the desktop shows the picture."""
import unittest

from helpers import fake_home, make_image

try:
    from wallrice.ui import common, picker
except (ImportError, ValueError) as e:
    picker = common = None
    SKIP = str(e)
else:
    SKIP = ""

from wallrice import collections
from wallrice.state import load_review, save_review


@unittest.skipIf(picker is None, f"needs GTK 3 + cairo: {SKIP}")
class Picker(unittest.TestCase):
    def view(self, home, current=1, kinds=("colour", "bright", "grey", "colour")):
        items = [make_image(home / f"Pictures/walls/space/p{i}.png", k) for i, k in enumerate(kinds)]
        items = collections.all_pictures()
        v = picker.PickerView(640, 360, 1, items, items[current] if current is not None else None, now=0.0)
        v.set_current(None, None, now=0.0)
        v.phase = "browse"
        return v, items

    def test_opens_on_the_current_wallpaper(self):
        with fake_home() as home:
            v, items = self.view(home, current=2)
            self.assertEqual(v.selected_path(), items[2])

    def test_jobs_by_priority(self):
        with fake_home() as home:
            v, items = self.view(home, current=1)
            jobs = v.jobs()
            self.assertEqual(jobs[:3], [("card", 1), ("theme", 1), ("blur", 1)])
            self.assertLess(jobs.index(("thumb", 3)), jobs.index(("full", 1)))

    def test_delete_and_undo_restore_exactly(self):
        """A picture kept in the review goes back to Keep after Ctrl+Z, not to "unreviewed"."""
        with fake_home() as home:
            v, items = self.view(home, current=0)
            save_review({"keep": {"space/p0.png"}, "drop": set()})
            self.assertTrue(v.remove_selected(now=1.0))
            r = load_review()
            self.assertEqual((r["keep"], r["drop"]), (set(), {"space/p0.png"}))
            self.assertNotIn(0, v.view)
            self.assertTrue(v.undo_remove(now=2.0))
            r = load_review()
            self.assertEqual((r["keep"], r["drop"]), ({"space/p0.png"}, set()))
            # an unreviewed one goes back to unreviewed
            v.select(v.view.index(1), now=3.0)
            v.remove_selected(now=3.0)
            v.undo_remove(now=4.0)
            r = load_review()
            self.assertEqual((r["keep"], r["drop"]), ({"space/p0.png"}, set()))

    def test_double_delete_removes_one(self):
        with fake_home() as home:
            v, _ = self.view(home)
            self.assertTrue(v.remove_selected(now=1.0))
            self.assertFalse(v.remove_selected(now=1.1))
            self.assertEqual(len(load_review()["drop"]), 1)

    def test_esc_after_removing_the_current_one_applies_the_one_on_show(self):
        with fake_home() as home:
            v, items = self.view(home, current=1)
            v.remove_selected(now=1.0)
            self.assertTrue(v.current_removed)
            path = v.escape(now=2.0)
            self.assertEqual(path, v.items[v.view[v.sel]])
            self.assertNotEqual(path, items[1])
            self.assertEqual(v.phase, "confirm")

    def test_esc_otherwise_goes_back(self):
        with fake_home() as home:
            v, _ = self.view(home)
            v.query = "zzz"
            self.assertIsNone(v.escape(now=1.0))
            self.assertEqual((v.query, v.phase), ("", "browse"), "Esc first clears the search")
            v.escape(now=1.5)
            self.assertEqual(v.phase, "cancel")
            busy, code = v.tick(3.0)
            self.assertEqual(code, 1)

    def test_search_tokens(self):
        with fake_home() as home:
            v, items = self.view(home)
            v.set_query("space p2", now=1.0)
            self.assertEqual([v.items[i] for i in v.view], [items[2]])
            v.set_query("nothing-like-this", now=1.1)
            self.assertEqual(v.view, [])

    def test_confirm_waits_for_the_desktop(self):
        with fake_home() as home:
            v, items = self.view(home)
            self.assertEqual(v.start_confirm(now=1.0), items[1])
            self.assertIsNone(v.tick(2.0)[1], "apply hasn't finished")
            v.applied(0, settle=1.0, now=2.0)
            self.assertIsNone(v.tick(2.5)[1], "GNOME is still cross-fading underneath")
            self.assertEqual(v.tick(3.1)[1], 0)

    def test_draws_every_phase_offscreen(self):
        with fake_home() as home:
            v, items = self.view(home)
            while (job := v.next_job()) is not None:
                v.loaded(job[0], job[1], v.compute(*job), now=0.5)
            for t, act in ((1.0, None), (1.2, "remove"), (1.5, "tab"), (2.0, "confirm"), (2.3, None)):
                if act == "remove":
                    v.remove_selected(now=t)
                elif act == "tab":
                    v.toggle_mock(now=t)
                elif act == "confirm":
                    v.start_confirm(now=t)
                v.tick(t)
                common.save_png(lambda cr, t=t: v.draw(cr, t), 640, 360, home / f"f{t}.png")
            self.assertTrue((home / "f2.3.png").stat().st_size > 1000)


if __name__ == "__main__":
    unittest.main()
