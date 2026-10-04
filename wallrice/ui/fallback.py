"""The picker without GTK: a rofi, wofi or fuzzel grid of thumbnails, or fzf with chafa previews
in a terminal."""
import shutil
import subprocess
import sys

from .. import collections, engine
from ..state import load_state


def label(p):
    src, folder, title, _credit = collections.describe(p)
    return f"{src}{' · ' + folder if folder else ''} · {title}"


def choose(pics):
    labels = [label(p) for p in pics]
    thumbs = [collections.thumb_path(p) for p in pics]
    if shutil.which("rofi"):
        lines = "".join(f"{l}\0icon\x1f{t}\n" for l, t in zip(labels, thumbs))
        cmd = ["rofi", "-dmenu", "-i", "-show-icons", "-p", "wallpaper", "-format", "i"]
    elif shutil.which("fuzzel"):
        lines = "".join(f"{l}\0icon\x1f{t}\n" for l, t in zip(labels, thumbs))
        cmd = ["fuzzel", "--dmenu", "--index", "--prompt", "wallpaper: "]
    elif shutil.which("wofi"):
        lines = "".join(f"img:{t}:text:{i}\t{l}\n" for i, (l, t) in enumerate(zip(labels, thumbs)))
        cmd = ["wofi", "--dmenu", "--allow-images", "--prompt", "wallpaper"]
    elif shutil.which("fzf") and sys.stdin.isatty():
        lines = "".join(f"{i}\t{l}\t{t}\n" for i, (l, t) in enumerate(zip(labels, thumbs)))
        preview = "chafa --size=${FZF_PREVIEW_COLUMNS}x${FZF_PREVIEW_LINES} {3}" if shutil.which("chafa") else "echo {3}"
        cmd = ["fzf", "--delimiter", "\t", "--with-nth", "2", "--preview", preview, "--preview-window", "right:60%"]
    else:
        print("wallrice: no picker available: install GTK 3 for Python (see wallrice doctor), or rofi, wofi, "
              "fuzzel or fzf", file=sys.stderr)
        return None
    p = subprocess.run(cmd, input=lines, stdout=subprocess.PIPE, text=True)
    out = p.stdout.strip()
    if p.returncode != 0 or not out:
        return None
    if cmd[0] in ("wofi", "fzf"):
        out = out.split("\t", 1)[0].split(":")[-1]
    try:
        return pics[int(out)]
    except (ValueError, IndexError):
        return None


def pick():
    pics = collections.wallpapers(load_state().get("mode", "all"))
    if not pics:
        print("wallrice: no wallpapers yet: run  wallrice walls update", file=sys.stderr)
        return 1
    collections.build_thumbs(pics)
    choice = choose(pics)
    if choice is None:
        return 1
    try:
        engine.apply(choice)
    except engine.ApplyError as e:
        print(f"wallrice: {e}", file=sys.stderr)
        return 1
    return 0
