"""The command line: help, settings commands, the timer tick, and the installers' dry runs."""
import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from helpers import fake_home, make_image

from wallrice import cli, collections, engine, setup
from wallrice.state import load_state

ROOT = Path(__file__).resolve().parent.parent


def run_cli(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class Commands(unittest.TestCase):
    def test_help_and_version(self):
        p = subprocess.run([str(ROOT / "bin" / "wallrice"), "--version"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("wallrice", p.stdout)
        self.assertIn("walls update", cli.__doc__)

    def test_settings(self):
        with fake_home(), mock.patch.object(setup, "set_rotation", lambda *a, **k: None):
            self.assertEqual(run_cli("animations", "off")[0], 0)
            self.assertFalse(load_state()["animations"])
            run_cli("pause")
            self.assertTrue(load_state()["paused"])
            run_cli("resume")
            self.assertFalse(load_state()["paused"])
            run_cli("rotate", "15m")
            self.assertEqual(load_state()["rotate_minutes"], 15)
            run_cli("rotate", "off")
            self.assertEqual(load_state()["rotate_minutes"], 0)
            code, out = run_cli("status")
            self.assertEqual(json.loads(out)["rotate_minutes"], 0)

    def test_next_only_rotates_collections(self):
        """The timer never swaps in the distro's default wallpapers: only downloaded collections."""
        with fake_home() as home, mock.patch.object(engine, "apply") as apply:
            run_cli("next")
            apply.assert_not_called()
            make_image(home / "Pictures/walls/space/a.png")
            make_image(home / "Pictures/walls/space/b.png")
            run_cli("next")
            apply.assert_called_once()
            self.assertTrue(collections.in_walls(apply.call_args[0][0]))

    def test_next_does_nothing_when_paused(self):
        with fake_home() as home, mock.patch.object(engine, "apply") as apply, \
                mock.patch.object(setup, "set_rotation", lambda *a, **k: None):
            make_image(home / "Pictures/walls/space/a.png")
            run_cli("pause")
            run_cli("next")
            apply.assert_not_called()


class Installers(unittest.TestCase):
    def test_dry_runs_change_nothing(self):
        with fake_home() as home:
            env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "XDG_CURRENT_DESKTOP": "GNOME",
                   "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CONFIG_HOME": str(home / ".config"),
                   "XDG_CACHE_HOME": str(home / ".cache"), "WALLRICE_WALLS": str(home / "walls")}
            for script in ("install.sh", "uninstall.sh"):
                p = subprocess.run(["bash", str(ROOT / script), "--dry-run", "--no-packages"] if script == "install.sh"
                                   else ["bash", str(ROOT / script), "--dry-run"],
                                   capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL, timeout=60)
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            made = [p for d in (".config", ".local", "walls") for p in (home / d).rglob("*") if p.is_file()]
            made += [p for p in (home / ".cache").rglob("*") if p.is_file() and "wallrice" in p.parts
                     and "palettes" not in p.parts]
            self.assertEqual(made, [], "a dry run writes nothing")


if __name__ == "__main__":
    unittest.main()
