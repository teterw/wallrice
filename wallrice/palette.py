"""16 colours from a wallpaper, laid out like a terminal scheme: color0 is the background, color15
the text, color1-6 the picture's colours and color9-14 lighter versions of them.

wallust is used when it's installed (it's packaged on Arch; most distros don't have it). Otherwise a
built-in extractor does the same job with Pillow, so this works on every machine. Either way the
result is kept in a small cache of our own, so the picker's preview and the applied theme match."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from . import paths
from .color import WHITE, hls, hue_distance, luminance, mix, rgb2hex
from .state import write_atomic

WALLUST = ["wallust", "run", "-N", "-s", "-T", "-n", "-q", "-b", "fastresize", "-c", "salience",
           "-p", "saliencedark", "-k", "--print-scheme"]  # -n: wallust's own cache grows by MBs per image


class PaletteError(Exception):
    pass


def cache_path(img):
    img = Path(img)
    st = img.stat()
    key = hashlib.sha1(f"{img}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()
    return paths.cache() / "palettes" / f"{key}.json"


def extract(img, use_wallust=None):
    """The image's palette: {"color0".."color15", "background", "foreground", "cursor"}."""
    img = Path(img)
    cache = cache_path(img)
    try:
        return json.loads(cache.read_text())
    except (OSError, ValueError):
        pass
    if use_wallust is None:
        use_wallust = shutil.which("wallust") is not None
    hexes = None
    if use_wallust:
        try:
            hexes = run_wallust(img)
        except PaletteError:
            hexes = None  # fall through to the built-in extractor
    if hexes is None:
        hexes = pillow_palette(img)
    pal = {f"color{i}": h for i, h in enumerate(hexes[:16])}
    pal.update(background=hexes[0], foreground=hexes[15], cursor=hexes[7])
    write_atomic(cache, json.dumps(pal))
    return pal


def run_wallust(img):
    try:
        p = subprocess.run([*WALLUST, str(img)], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PaletteError(f"wallust: {e}") from e
    hexes = [l.strip() for l in p.stdout.splitlines() if l.strip().startswith("#")]
    if p.returncode != 0 or len(hexes) < 16:
        why = (p.stderr.strip() or "no output").splitlines()[0]
        raise PaletteError(f"wallust couldn't read colours from {img}: {why}")
    return hexes[:16]


def pillow_palette(img):
    """Quantize a small copy to 16 colours, then lay them out like wallust's dark schemes."""
    try:
        from PIL import Image
    except ImportError as e:
        raise PaletteError("needs Pillow (python3-pillow) or wallust") from e
    try:
        with Image.open(img) as im:
            im.draft("RGB", (512, 512))  # JPEG: decode at a reduced size straight away
            im = im.convert("RGB")
            im.thumbnail((256, 256))
    except OSError as e:
        raise PaletteError(f"can't read {img}: {e}") from e
    q = im.quantize(colors=16, method=Image.Quantize.MEDIANCUT)
    flat = q.getpalette()[:48]
    counts = q.getcolors() or []
    total = sum(n for n, _ in counts) or 1
    cols = []
    for n, idx in counts:
        rgb = tuple(v / 255 for v in flat[idx * 3:idx * 3 + 3])
        if len(rgb) == 3:
            cols.append((rgb, n / total))
    return layout(cols)


def layout(cols):
    """[(rgb, share)] -> 16 hex colours. Background: the darkest of the main colours (the picture's
    shadows, which keep its mood); text: the lightest; colours 1-6: the most salient hues."""
    if not cols:
        cols = [((0.5, 0.5, 0.5), 1.0)]
    cols.sort(key=lambda c: -c[1])
    main = [c for c in cols if c[1] >= 0.03] or cols[:1]
    bg = min(main, key=lambda c: luminance(c[0]))[0]
    fg = max(cols, key=lambda c: luminance(c[0]))[0]
    while luminance(fg) < 0.6:  # text near white, keeping a trace of the picture's tint
        fg = mix(fg, WHITE, 0.3)

    def salience(c):
        rgb, share = c
        _, l, s = hls(rgb)
        if l < 0.08 or l > 0.95:
            return 0.0
        return s * (share ** 0.35) * (1 - abs(l - 0.55) * 0.8)
    picks = []
    for rgb, _share in sorted(cols, key=salience, reverse=True):
        h = hls(rgb)[0]
        if all(hue_distance(h, hls(p)[0]) > 0.04 or hls(p)[2] < 0.1 for p in picks):
            picks.append(rgb)
        if len(picks) == 6:
            break
    for rgb, _ in cols:  # fewer than six distinct hues: fill with the remaining colours
        if len(picks) == 6:
            break
        if rgb not in picks:
            picks.append(rgb)
    while len(picks) < 6:
        picks.append(picks[len(picks) % max(1, len(picks))] if picks else mix(bg, fg, 0.5))
    bright = [mix(c, WHITE, 0.25) for c in picks]
    out = [bg, *picks, mix(fg, bg, 0.2), mix(bg, fg, 0.35), *bright, fg]
    return [rgb2hex(c) for c in out]
