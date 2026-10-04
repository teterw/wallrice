"""Shared test helpers: sample palettes, a throwaway home directory, small generated images."""
import contextlib
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def palette(bg, fg, colors):
    p = {"background": bg, "foreground": fg, "cursor": fg}
    p.update({f"color{i}": c for i, c in enumerate(colors)})
    return p


BRIGHT = palette("#f2efe9", "#2a2a2a", ["#e8e4dc", "#e9a3a3", "#a3d9a5", "#f2e2a0", "#a7c7e7", "#d7b4e8", "#a8e0dc", "#ffffff"] * 2)
DARK = palette("#101418", "#d6dde3", ["#101418", "#c0392b", "#27ae60", "#f1c40f", "#2980b9", "#8e44ad", "#16a085", "#ecf0f1"] * 2)
GREY = palette("#3a3a3a", "#9a9a9a", ["#3a3a3a", "#505050", "#5a5a5a", "#646464", "#6e6e6e", "#787878", "#828282", "#9a9a9a"] * 2)


@contextlib.contextmanager
def fake_home(**extra_env):
    """A temporary $HOME with XDG dirs inside it, and nothing from the real desktop leaking in."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        env = {"HOME": tmp, "XDG_CONFIG_HOME": f"{tmp}/.config", "XDG_CACHE_HOME": f"{tmp}/.cache",
               "XDG_DATA_HOME": f"{tmp}/.local/share", "XDG_RUNTIME_DIR": f"{tmp}/run",
               "WALLRICE_WALLS": f"{tmp}/Pictures/walls"}
        env.update(extra_env)
        with mock.patch.dict(os.environ, env):
            yield home


def make_image(path, kind="colour", size=(320, 180)):
    from PIL import Image, ImageDraw
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    w, h = size
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    for x in range(w):
        t = x / (w - 1)
        if kind == "grey":
            v = int(40 + 180 * t)
            col = (v, v, v)
        elif kind == "bright":
            col = (int(235 + 20 * t), int(225 + 20 * t), int(200 + 40 * t))
        else:  # a dusky sky: deep blue into orange, with a magenta band
            col = (int(20 + 220 * t), int(30 + 90 * t), int(90 - 60 * t))
        d.line([(x, 0), (x, h)], fill=col)
    if kind == "colour":
        d.rectangle([w // 3, h // 3, w // 2, h // 2], fill=(200, 40, 160))
    im.save(path)
    return path
