"""Shared pieces of wallrice's screens: easing and tweens, picture loading into cairo surfaces, drawing
helpers, fonts, and the key guard that keeps auto-repeat from making choices.

Everything is drawn with cairo on the CPU, so it works on X11 and Wayland, with or without GPU
drivers; pictures are decoded with Pillow (JPEG at a reduced size straight away)."""
import functools
import math
import time
from pathlib import Path

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402
from PIL import Image, ImageFilter, ImageOps  # noqa: E402

from .. import collections  # noqa: E402

# Colours of the review and of the picker before a theme has loaded (the violet brand)
THEME = {"bg": (0.043, 0.039, 0.071), "surface": (0.10, 0.09, 0.15), "fg": (0.93, 0.91, 0.96),
         "muted": (0.58, 0.55, 0.68), "keep": (0.545, 0.361, 0.965), "remove": (0.957, 0.247, 0.369)}


# ---------------------------------------------------------------- fonts

@functools.lru_cache(maxsize=None)
def families():
    return {f.get_name() for f in PangoCairo.FontMap.get_default().list_families()}


@functools.lru_cache(maxsize=None)
def font(kind="sans"):
    wanted = {"sans": ("Inter", "Adwaita Sans", "Cantarell", "Noto Sans", "DejaVu Sans"),
              "mono": ("JetBrainsMono Nerd Font", "JetBrains Mono", "Adwaita Mono", "Noto Sans Mono", "DejaVu Sans Mono",
                       "Source Code Pro")}[kind]
    have = families()
    return next((f for f in wanted if f in have), "monospace" if kind == "mono" else "sans-serif")


# ---------------------------------------------------------------- animation

def clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def lerp(a, b, t):
    return a + (b - a) * t


class Tween:
    """A value going from a to b over dur seconds."""

    def __init__(self, a=0.0, b=1.0, dur=0.3, ease=ease_out, now=None):
        self.a, self.b, self.dur, self.ease = a, b, max(dur, 1e-6), ease
        self.t0 = time.monotonic() if now is None else now

    def progress(self, now):
        return clamp((now - self.t0) / self.dur)

    def value(self, now):
        return lerp(self.a, self.b, self.ease(self.progress(now)))

    def done(self, now):
        return now - self.t0 >= self.dur


class KeyGuard:
    """One press, one action. A held key auto-repeats, and on a busy machine a late key release made
    the X server repeat by itself (it once removed 13 pictures in a test). So: a press of a key
    that's still down (within 700 ms of its last press, no release in between) is ignored, and
    actions are at least `gap` seconds apart, so a double-click counts once."""

    REPEAT_MS = 700

    def __init__(self, gap=0.2):
        self.down, self.gap, self.last_action = {}, gap, -1e9

    def press(self, key, time_ms):
        """True if this press is a fresh one (not auto-repeat)."""
        last = self.down.get(key)
        self.down[key] = time_ms
        return last is None or time_ms - last >= self.REPEAT_MS

    def release(self, key):
        self.down.pop(key, None)

    def act(self, now=None):
        """True if an action may happen now (and records it)."""
        now = time.monotonic() if now is None else now
        if now - self.last_action < self.gap:
            return False
        self.last_action = now
        return True


# ---------------------------------------------------------------- pictures

def surface(im, scale=1):
    """PIL image -> cairo surface (cairo keeps premultiplied BGRA in memory on little-endian PCs)."""
    im = im.convert("RGBA")
    w, h = im.size
    s = cairo.ImageSurface.create_for_data(bytearray(im.tobytes("raw", "BGRa")), cairo.FORMAT_ARGB32, w, h, w * 4)
    if scale != 1:
        s.set_device_scale(scale, scale)
    return s


def cover(path, w, h, scale=1):
    """The picture as "zoom/fill" shows it on a w x h screen: scaled to cover, centre-cropped."""
    W, H = int(w * scale), int(h * scale)
    with Image.open(path) as im:
        im.draft("RGB", (W, H))  # JPEG: decode at a reduced size straight away
        return surface(ImageOps.fit(im.convert("RGB"), (W, H), Image.BILINEAR), scale)


def contain(path, w, h, scale=1):
    """The whole picture, fitted inside w x h (never enlarged). Returns (surface, original size)."""
    W, H = int(w * scale), int(h * scale)
    with Image.open(path) as im:
        size = im.size
        im.draft("RGB", (W, H))
        im = im.convert("RGB")
        im.thumbnail((W, H), Image.LANCZOS)
        return surface(im, scale), size


def thumb(path):
    t = collections.thumb_path(path)
    if not t.exists():
        collections.build_thumbs([path])  # cached for next time
    with Image.open(t if t.exists() else path) as im:
        im.draft("RGB", collections.THUMB)
        return surface(ImageOps.fit(im.convert("RGB"), collections.THUMB, Image.BILINEAR))


def blurred(path, w, h):
    """A tiny blurred copy; cairo scales it up into a soft backdrop."""
    t = collections.thumb_path(path)
    with Image.open(t if t.exists() else path) as im:
        im.draft("RGB", collections.THUMB)
        small = ImageOps.fit(im.convert("RGB"), (max(16, int(w) // 14), max(9, int(h) // 14)), Image.BILINEAR)
    return surface(small.filter(ImageFilter.GaussianBlur(2.2)))


# ---------------------------------------------------------------- drawing

def paint_scaled(cr, src, x, y, w, h, alpha=1.0, filt=cairo.FILTER_BILINEAR):
    sx, sy = src.get_device_scale()
    sw, sh = src.get_width() / sx, src.get_height() / sy
    cr.save()
    cr.translate(x, y)
    cr.scale(w / sw, h / sh)
    cr.set_source_surface(src, 0, 0)
    cr.get_source().set_filter(filt)
    cr.get_source().set_extend(cairo.EXTEND_PAD)
    cr.paint_with_alpha(alpha)
    cr.restore()


def size_of(src):
    sx, sy = src.get_device_scale()
    return src.get_width() / sx, src.get_height() / sy


def rrect(cr, x, y, w, h, r):
    r = max(0.0, min(r, w / 2, h / 2))
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def text(cr, s, x, y, size, color, alpha=1.0, weight="", kind="sans", align="left", width=None):
    layout = PangoCairo.create_layout(cr)
    layout.set_font_description(Pango.FontDescription(f"{font(kind)} {weight} {size:.1f}px"))
    layout.set_text(s, -1)
    if width:
        layout.set_width(int(width * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
    w, h = layout.get_pixel_size()
    if align == "center":
        x -= w / 2
    elif align == "right":
        x -= w
    cr.set_source_rgba(*color, alpha)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)
    return w, h


def shadow(cr, x, y, w, h, r, alpha, steps=6, spread=3, drop=10):
    for i in range(steps):
        rrect(cr, x - i * spread, y - i * spread + drop, w + i * spread * 2, h + i * spread * 2, r + i * spread)
        cr.set_source_rgba(0, 0, 0, alpha)
        cr.fill()


def pretty(path):
    """(label, title): "SPACE" / "ROSE-PINE · PHOTOGRAPHY", and the picture's title."""
    src, folder, title, _credit = collections.describe(path)
    return (f"{src} · {folder}" if folder else src), title


def screen_size(display=None):
    """(width, height, scale) of the monitor the screens open on: the one under the pointer on X11,
    the primary (or first) one otherwise. Wayland places fullscreen windows itself."""
    from gi.repository import Gdk
    display = display or Gdk.Display.get_default()
    mon = None
    try:
        _, px, py = display.get_default_seat().get_pointer().get_position()
        if px or py:
            mon = display.get_monitor_at_point(px, py)
    except Exception:  # noqa: BLE001
        mon = None
    mon = mon or display.get_primary_monitor() or (display.get_monitor(0) if display.get_n_monitors() else None)
    if mon is None or mon.get_geometry().width < 200 or mon.get_geometry().height < 200:
        return 1280, 720, 1  # a backend that reports no real monitor (broadway, some VMs): the window resizes later
    g = mon.get_geometry()
    return g.width, g.height, mon.get_scale_factor()


def save_png(draw, w, h, path):
    """Render one frame offscreen (for tests and contact sheets of the animations)."""
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w), int(h))
    cr = cairo.Context(s)
    draw(cr)
    s.write_to_png(str(path))
    return Path(path)
