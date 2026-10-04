"""The picker (Super+W): a full-screen preview screen.

It opens by shrinking the current wallpaper, drawn exactly as the desktop shows it, into a preview
card with the screen's shape, over a blurred backdrop. Browse the filmstrip (spring scrolling) and
the card cross-fades to each picture, with a mock of the themed desktop drawn on it at real size and
the palette underneath, everything recolouring smoothly. Enter grows the chosen picture back to full
screen while the theme is applied underneath, so the hand-over to the desktop is seamless. Esc goes
back the same way.

Delete (or the card's ✕) removes the highlighted wallpaper: it's recorded like a Remove in the
review, so it stays gone after updates, and the file leaves the disk when the picker closes.
Ctrl+Z restores the exact previous choice. A held Delete acts once; arrow keys repeat on purpose."""
import math
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
import cairo  # noqa: E402
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import backends, barstyles, collections, detect, engine, palette  # noqa: E402
from ..color import rgb2hex  # noqa: E402
from ..state import load_review, load_state, save_review  # noqa: E402
from ..theme import derive, mix_theme  # noqa: E402
from .common import (THEME, KeyGuard, Tween, blurred, clamp, cover, ease_in_out, ease_out, lerp,  # noqa: E402
                     paint_scaled, pretty, rrect, screen_size, shadow, text, thumb)

BRAND_THEME = derive({"background": "#0b0a12", "foreground": "#ece9f4", **{f"color{i}": "#8b5cf6" for i in range(16)}})
MOVES = {"Right": 1, "Down": 1, "Left": -1, "Up": -1, "Page_Down": 8, "Page_Up": -8}


def theme_of(path):
    try:
        return derive(palette.extract(path))
    except Exception:  # noqa: BLE001 - unreadable: the picture just doesn't recolour the preview
        return None


class PickerView:
    """The picker's state, loading plan, input actions and drawing, without a window."""

    LRU = {"card": 10, "full": 3, "blur": 12, "thumb": 160, "theme": 400}

    def __init__(self, W, H, scale=1, items=None, current=None, mode="all", animate=True, now=None):
        now = time.monotonic() if now is None else now
        self.W, self.H, self.scale = W, H, scale
        self.animate, self.mode = animate, mode
        self.items = list(items or [])
        self.names = [f"{collections.rel(p)} {pretty(p)[1]}".lower() for p in self.items]
        self.view = list(range(len(self.items)))
        self.query = ""
        self.current = Path(current) if current and Path(current).is_file() else None
        self.sel = next((i for i, p in enumerate(self.items) if p == self.current), 0)
        self.exit_code = 1
        self.cw, self.ch = int(W * 0.56), int(H * 0.56)  # the card has the screen's shape: the zoom is a pure scale
        self.cx, self.cy = (W - self.cw) / 2, H * 0.095
        self.cache = {k: OrderedDict() for k in self.LRU}
        self.loaded_at = {}
        self.lock = threading.Lock()
        self.inflight = set()
        self.cur_full = None
        self.theme_from = self.theme_to = BRAND_THEME
        self.theme_tw = Tween(1, 1, 0.01, now=now)
        self.layers, self.backs = [], []
        self.pos = float(self.sel)
        self.phase, self.phase_tw = "open", Tween(0, 1, self.d(0.6), ease_out, now=now)
        self.mock_tw = Tween(1, 1, 0.01, now=now)
        self.apply_done, self.settle, self.target = None, 0.0, None
        self.gone, self.removed, self.dropping, self.gap = set(), [], [], None
        self.toast, self.last_remove = None, -1e9
        self.remove_btn, self.hover_remove, self.current_removed = None, False, False
        self.guard = KeyGuard(gap=0.25)
        self.bar_style = barstyles.get(load_state().get("bar_style"))
        self.last = now

    def d(self, seconds):
        """An animation's length, or (almost) nothing with animations off."""
        return seconds if self.animate else 0.01

    def set_current(self, surface, theme, now=None):
        """The wallpaper on the desktop now: the opening starts from it."""
        self.cur_full = surface
        if theme:
            self.theme_from = self.theme_to = theme
        if surface is not None:
            self.layers = [{"src": surface, "tw": Tween(1, 1, 0.01, now=now)}]
        if self.items:
            self.select(self.sel, fade=False, now=now)

    # ---------------------------------------------------------------- background loading

    def jobs(self):
        """What to load next, by priority: the selected picture's card, theme and backdrop, then the
        filmstrip around it, then its full-screen picture, then the neighbours."""
        if not self.view:
            return []
        s = self.view[self.sel]
        near = [self.view[self.sel + d] for d in (1, -1, 2, -2) if 0 <= self.sel + d < len(self.view)]
        film = [self.view[self.sel + d] for d in range(-9, 10) if 0 <= self.sel + d < len(self.view)]
        out = [("card", s), ("theme", s), ("blur", s)] + [("thumb", i) for i in film] + [("full", s)]
        out += [(k, i) for i in near for k in ("card", "theme", "blur")]
        return out

    def next_job(self):
        with self.lock:
            for job in self.jobs():
                if job not in self.inflight and job[1] not in self.cache[job[0]]:
                    self.inflight.add(job)
                    return job
        return None

    def compute(self, kind, idx):
        path = self.items[idx]
        try:
            return {"card": lambda: cover(path, self.cw, self.ch, self.scale),
                    "full": lambda: cover(path, self.W, self.H, self.scale),
                    "blur": lambda: blurred(path, self.W, self.H), "thumb": lambda: thumb(path),
                    "theme": lambda: theme_of(path)}[kind]()
        except Exception:  # noqa: BLE001 - an unreadable picture just stays a placeholder
            return None

    def loaded(self, kind, idx, res, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            self.inflight.discard((kind, idx))
            c = self.cache[kind]
            c[idx] = res
            while len(c) > self.LRU[kind]:
                c.popitem(last=False)
        self.loaded_at[(kind, idx)] = now
        if self.view and idx == self.view[self.sel] and res is not None:
            if kind == "card" and self.phase == "browse":
                self.push_layer(res, now=now)  # the thumbnail sharpens into the full picture
            elif kind == "blur":
                self.backs.append({"src": res, "tw": Tween(0, 1, self.d(0.45), now=now)})
            elif kind == "theme":
                self.retheme(res, now)

    def get(self, kind, idx):
        c = self.cache[kind]
        if idx in c:
            c.move_to_end(idx)
            return c[idx]
        return None

    # ---------------------------------------------------------------- state changes

    def push_layer(self, src, dur=0.28, now=None):
        self.layers.append({"src": src, "tw": Tween(0, 1, self.d(dur), now=now)})

    def theme_now(self, now):
        return mix_theme(self.theme_from, self.theme_to, self.theme_tw.value(now))

    def retheme(self, theme, now=None):
        now = time.monotonic() if now is None else now
        self.theme_from, self.theme_to = self.theme_now(now), theme
        self.theme_tw = Tween(0, 1, self.d(0.45), ease_in_out, now=now)

    def select(self, sel, fade=True, now=None):
        if not self.view:
            return
        self.sel = max(0, min(len(self.view) - 1, sel))
        idx = self.view[self.sel]
        src = self.get("card", idx) or self.get("thumb", idx)
        if src is not None and fade:
            self.push_layer(src, now=now)
        th = self.get("theme", idx)
        if th:
            self.retheme(th, now)
        b = self.get("blur", idx)
        if b is not None:
            self.backs.append({"src": b, "tw": Tween(0, 1, self.d(0.45), now=now)})

    def set_query(self, q, now=None):
        self.query = q
        toks = q.lower().split()
        keep = self.view[self.sel] if self.view else None
        self.view = [i for i, n in enumerate(self.names) if i not in self.gone and all(t in n for t in toks)]
        new = self.view.index(keep) if keep in self.view else 0
        self.pos = new - 0.6 if self.view else 0.0
        self.select(new, now=now)

    def selected_path(self):
        return self.items[self.view[self.sel]] if self.view else None

    def start_confirm(self, now=None):
        """Enter: returns the picture to apply, or None. The UI fades and the card grows to full screen."""
        if not self.view or self.phase != "browse":
            return None
        self.target = self.view[self.sel]
        self.phase, self.phase_tw = "confirm", Tween(0, 1, self.d(0.65), ease_in_out, now=now)
        return self.items[self.target]

    def applied(self, code, settle=0.0, now=None):
        self.exit_code, self.settle = code, settle
        self.apply_done = time.monotonic() if now is None else now

    def remove_selected(self, now=None):
        """Delete or ✕: this wallpaper goes. Saved like a Remove in the review; Ctrl+Z brings it back."""
        now = time.monotonic() if now is None else now
        if self.phase != "browse" or not self.view or now - self.last_remove < 0.25:
            return False  # 0.25 s apart at least: a double-click removes one
        idx = self.view[self.sel]
        path = self.items[idx]
        if not collections.in_walls(path):
            self.toast = ("Only wallpapers in your walls folder can be removed here", now)
            return False
        self.last_remove = now
        review = load_review()
        rel = collections.rel(path)
        was_kept = rel in review["keep"]  # Ctrl+Z puts it back exactly as it was
        review["drop"].add(rel)
        review["keep"].discard(rel)
        save_review(review)
        self.removed.append((idx, was_kept))
        self.gone.add(idx)
        self.current_removed = self.current_removed or path == self.current
        src = self.get("card", idx) or self.get("thumb", idx)
        if src is not None:  # the card drops away; the next picture fades in behind it
            self.dropping.append({"src": src, "tw": Tween(0, 1, self.d(0.5), ease_in_out, now=now)})
        self.view.pop(self.sel)
        self.gap = (self.sel, Tween(1, 0, self.d(0.3), now=now))  # the filmstrip closes up
        self.layers = []
        if self.view:
            self.select(min(self.sel, len(self.view) - 1), now=now)
        self.toast = (f"Removed “{pretty(path)[1]}”   ·   Ctrl+Z to undo", now)
        return True

    def undo_remove(self, now=None):
        now = time.monotonic() if now is None else now
        if self.phase != "browse" or not self.removed:
            return False
        idx, was_kept = self.removed.pop()
        path = self.items[idx]
        review = load_review()
        rel = collections.rel(path)
        review["drop"].discard(rel)
        if was_kept:
            review["keep"].add(rel)
        save_review(review)
        self.gone.discard(idx)
        if path == self.current:
            self.current_removed = False
        self.set_query(self.query, now)
        if idx in self.view:
            self.select(self.view.index(idx), now=now)
        self.toast = (f"Restored “{pretty(path)[1]}”", now)
        return True

    def cancel(self, now=None):
        if self.phase not in ("browse", "open"):
            return False
        if self.cur_full is not None:
            self.push_layer(self.cur_full, 0.2, now=now)
        self.phase, self.phase_tw = "cancel", Tween(0, 1, self.d(0.5), ease_in_out, now=now)
        return True

    def escape(self, now=None):
        """Esc: clear the search, or go back. If the current wallpaper was removed, going back would
        zoom into a deleted picture, so Esc applies the one on show instead."""
        if self.query:
            self.set_query("", now)
            return None
        if self.current_removed and self.view:
            return self.start_confirm(now)
        self.cancel(now)
        return None

    def toggle_mock(self, now=None):
        now = time.monotonic() if now is None else now
        v = self.mock_tw.value(now)
        self.mock_tw = Tween(v, 0.0 if self.mock_tw.b > 0.5 else 1.0, self.d(0.25), now=now)

    # ---------------------------------------------------------------- animation clock

    def tick(self, now):
        """Advance; returns (busy, quit_code or None)."""
        dt, self.last = min(0.1, now - self.last), now
        busy = False
        if self.view:
            target = float(self.sel)
            if abs(target - self.pos) > 0.002:  # spring scrolling
                self.pos += (target - self.pos) * (1 - math.exp(-dt * 13)) if self.animate else target - self.pos
                busy = True
            else:
                self.pos = target
        for layers in (self.layers, self.backs):
            while len(layers) > 1 and layers[1]["tw"].done(now):
                layers.pop(0)  # fully covered by the next one
            busy = busy or any(not l["tw"].done(now) for l in layers)
        busy = busy or not self.theme_tw.done(now) or not self.mock_tw.done(now) or not self.phase_tw.done(now)
        busy = busy or any(now - t < 0.3 for t in self.loaded_at.values())
        self.dropping = [d for d in self.dropping if not d["tw"].done(now)]
        busy = busy or bool(self.dropping) or bool(self.gap and not self.gap[1].done(now))
        busy = busy or bool(self.toast and now - self.toast[1] < 3.6)
        if self.phase == "open" and self.phase_tw.done(now):
            self.phase = "browse"
            if self.view:  # the opening showed the current wallpaper; settle on the selected one
                src = self.get("card", self.view[self.sel]) or self.get("thumb", self.view[self.sel])
                if src is not None:  # even the same picture: the card-sized copy is cheaper to draw
                    self.push_layer(src, now=now)
        if self.phase == "confirm" and self.phase_tw.done(now) and self.apply_done \
                and now - self.apply_done > max(0.25, self.settle):
            return busy, self.exit_code
        if self.phase == "cancel" and self.phase_tw.done(now):
            return busy, 1
        return busy or self.phase in ("confirm", "cancel", "open"), None

    # ---------------------------------------------------------------- pointer

    def film_geometry(self):
        tw = self.H * 0.16  # 16:9 thumbnails
        return tw, tw * 0.12, self.H * 0.85

    def over_remove(self, x, y):
        b = self.remove_btn
        return bool(b) and b[0] <= x <= b[0] + b[2] and b[1] <= y <= b[1] + b[3]

    def click(self, x, y, now=None):
        """Returns "confirm", "remove" or None (a filmstrip click selects)."""
        if self.phase != "browse":
            return None
        if self.over_remove(x, y):
            return "remove"
        if self.cx <= x <= self.cx + self.cw and self.cy <= y <= self.cy + self.ch:
            return "confirm"
        tw, gap, fy = self.film_geometry()
        if fy - tw * 0.3 <= y <= fy + tw * 0.75:
            d = round((x - self.W / 2) / (tw + gap) + self.pos - self.sel)
            if d:
                self.select(self.sel + d, now=now)
        return None

    # ---------------------------------------------------------------- drawing

    def card_rect(self, now):
        """Full screen while opening/closing, the card while browsing."""
        if self.phase == "open":
            t = self.phase_tw.value(now)
        elif self.phase in ("confirm", "cancel"):
            t = 1 - self.phase_tw.value(now)
        else:
            t = 1.0
        return lerp(0, self.cx, t), lerp(0, self.cy, t), lerp(self.W, self.cw, t), lerp(self.H, self.ch, t), t

    def ui_alpha(self, now):
        if self.phase == "open":  # the UI slides and fades in after the zoom has started
            return ease_out(clamp((self.phase_tw.progress(now) - 0.35) / 0.65))
        if self.phase in ("confirm", "cancel"):
            return 1 - ease_out(clamp(self.phase_tw.progress(now) / 0.45))
        return 1.0

    def draw(self, cr, now):
        th = self.theme_now(now)
        x, y, w, h, t = self.card_rect(now)
        ui = self.ui_alpha(now)
        cr.set_source_rgb(*th["bg"])
        cr.paint()
        if self.phase == "open" and self.cur_full is not None:
            paint_scaled(cr, self.cur_full, 0, 0, self.W, self.H)
        for b in self.backs:  # the selected picture, blurred and darkened
            a = b["tw"].value(now) * (t if self.phase in ("open", "cancel", "confirm") else 1.0)
            paint_scaled(cr, b["src"], 0, 0, self.W, self.H, a, cairo.FILTER_GOOD)
        cr.set_source_rgba(*th["bg"], 0.62 * t)
        cr.paint()
        if self.items:
            self.draw_card(cr, now, th, x, y, w, h, t)
        if ui > 0.01:
            self.draw_ui(cr, now, th, ui)

    def draw_card(self, cr, now, th, x, y, w, h, t):
        r = 18 * t
        if t > 0.02:
            shadow(cr, x, y, w, h, r, 0.07 * t)
        cr.save()
        rrect(cr, x, y, w, h, r)
        cr.clip()
        big = w > self.cw * 1.05
        target = self.target if self.phase == "confirm" else None
        for layer in self.layers:
            src = layer["src"]
            if big and target is not None:
                src = self.get("full", target) or self.get("card", target) or src
            paint_scaled(cr, src, x, y, w, h, layer["tw"].value(now), cairo.FILTER_BILINEAR if big else cairo.FILTER_GOOD)
        mock = self.mock_tw.value(now) * clamp((t - 0.55) / 0.45)
        if mock > 0.01:
            cr.save()
            cr.translate(x, y)
            cr.scale(w / self.W, h / self.H)
            draw_mock(cr, th, mock, self.W, self.H, self.bar_style)
            cr.restore()
        cr.restore()
        if t > 0.02:
            rrect(cr, x + 0.5, y + 0.5, w - 1, h - 1, r)
            cr.set_source_rgba(*th["accent"], 0.85 * t)
            cr.set_line_width(2)
            cr.stroke()
        for dr in self.dropping:  # a removed wallpaper falls away, tinted red
            k = dr["tw"].value(now)
            cr.save()
            cr.translate(x + w / 2, y + h / 2 + self.H * 0.5 * k)
            cr.rotate(-0.14 * k)
            cr.scale(1 - 0.15 * k, 1 - 0.15 * k)
            rrect(cr, -w / 2, -h / 2, w, h, r)
            cr.clip()
            paint_scaled(cr, dr["src"], -w / 2, -h / 2, w, h, 1 - k)
            cr.set_source_rgba(*THEME["remove"], 0.45 * (1 - k))
            cr.paint()
            cr.restore()
        self.remove_btn = None
        if self.phase == "browse" and self.view:  # ✕ in the card's corner removes the wallpaper
            br = max(14, self.H * 0.022)
            bx, by = x + w - br - 14, y + br + 14
            cr.arc(bx, by, br, 0, 2 * math.pi)
            cr.set_source_rgba(*(THEME["remove"] if self.hover_remove else (0, 0, 0)), 0.9 if self.hover_remove else 0.5)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.95)  # the ✕ itself, drawn: not every font has the glyph
            cr.set_line_width(max(2.0, br * 0.16))
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            k = br * 0.38
            cr.move_to(bx - k, by - k)
            cr.line_to(bx + k, by + k)
            cr.move_to(bx + k, by - k)
            cr.line_to(bx - k, by + k)
            cr.stroke()
            self.remove_btn = (bx - br, by - br, 2 * br, 2 * br)

    def draw_ui(self, cr, now, th, ui):
        W, H = self.W, self.H
        fg, muted, acc, s1 = th["fg"], th["muted"], th["accent"], th["surface"]
        slide = (1 - ui) * 24
        hy = H * 0.035 - slide  # header: title, search, count
        text(cr, "Wallpapers", self.cx, hy, H * 0.03, fg, ui, "Bold")
        qw = W * 0.26
        qx = W / 2 - qw / 2
        rrect(cr, qx, hy - 2, qw, H * 0.045, H * 0.0225)
        cr.set_source_rgba(*s1, 0.9 * ui)
        cr.fill()
        rrect(cr, qx, hy - 2, qw, H * 0.045, H * 0.0225)
        cr.set_source_rgba(*acc, (0.9 if self.query else 0.35) * ui)
        cr.set_line_width(1.5)
        cr.stroke()
        qs = H * 0.02
        if self.query:
            tw_, _ = text(cr, self.query, qx + 16, hy + H * 0.0225 - qs * 0.7, qs, fg, ui, width=qw - 40)
            cr.rectangle(qx + 18 + min(tw_, qw - 40), hy + H * 0.0225 - qs * 0.6, 2, qs * 1.2)
            cr.set_source_rgba(*acc, ui * (0.5 + 0.5 * math.cos(now * 5)))
            cr.fill()
        else:
            text(cr, "Type to search", qx + 16, hy + H * 0.0225 - qs * 0.7, qs, muted, ui)
        count = f"{len(self.view)} of {len(self.items)}  ·  {self.mode}"
        text(cr, count, self.cx + self.cw, hy + H * 0.008, H * 0.018, muted, ui, align="right")
        if not self.items:
            text(cr, "No wallpapers yet: run  wallrice walls update", W / 2, H * 0.45, H * 0.028, fg, ui, align="center")
            return
        if not self.view:
            text(cr, "Nothing matches", W / 2, self.cy + self.ch / 2, H * 0.03, fg, ui, "Bold", align="center")
        # the palette under the card
        py = self.cy + self.ch + H * 0.02 + slide * 0.5
        sw, gap = H * 0.05, H * 0.012
        swatches = (("Accent", acc), ("Background", th["bg"]), ("Surface", th["surface2"]), ("Text", fg), ("Muted", muted))
        term_w = H * 0.022
        total = len(swatches) * (sw * 2.6 + gap) + 8 * term_w + gap * 2
        x0 = W / 2 - total / 2
        for i, (lab, col) in enumerate(swatches):
            sx = x0 + i * (sw * 2.6 + gap)
            rrect(cr, sx, py, sw, sw * 0.62, 6)
            cr.set_source_rgba(*col, ui)
            cr.fill_preserve()
            cr.set_source_rgba(*fg, 0.25 * ui)
            cr.set_line_width(1)
            cr.stroke()
            text(cr, lab, sx + sw + 8, py - 1, H * 0.014, muted, ui)
            text(cr, rgb2hex(col), sx + sw + 8, py + H * 0.016, H * 0.014, fg, ui, kind="mono")
        tx = x0 + len(swatches) * (sw * 2.6 + gap) + gap
        for i, col in enumerate(th["term"]):
            cr.rectangle(tx + (i % 8) * term_w, py + (i // 8) * sw * 0.31, term_w - 2, sw * 0.31 - 2)
            cr.set_source_rgba(*col, ui)
            cr.fill()
        if not self.view:
            return
        cat, name = pretty(self.items[self.view[self.sel]])
        ny = py + sw * 0.62 + H * 0.016
        text(cr, cat.upper(), W / 2, ny, H * 0.0145, acc, ui, "Bold", align="center")
        text(cr, name, W / 2, ny + H * 0.021, H * 0.02, fg, ui, align="center", width=W * 0.6)
        self.draw_film(cr, now, th, ui, slide)
        if self.toast and now - self.toast[1] < 3.6:  # what Delete / Ctrl+Z just did
            a = ui * clamp((3.6 - (now - self.toast[1])) / 0.5)
            tw_ = min(W * 0.6, len(self.toast[0]) * H * 0.0105 + 40)
            rrect(cr, W / 2 - tw_ / 2, H * 0.905, tw_, H * 0.04, H * 0.02)
            cr.set_source_rgba(*th["surface2"], 0.96 * a)
            cr.fill()
            text(cr, self.toast[0], W / 2, H * 0.913, H * 0.017, fg, a, align="center", width=tw_ - 30)
        esc = "use this one" if self.current_removed else "back"
        hint = f"←  →  browse     type  search     Tab  preview     Delete  remove     Enter  apply     Esc  {esc}"
        text(cr, hint, W / 2, H * 0.955 + slide, H * 0.016, muted, ui * 0.9, align="center")

    def draw_film(self, cr, now, th, ui, slide):
        W = self.W
        acc, s1 = th["accent"], th["surface"]
        tw, gap, fy = self.film_geometry()
        fy += slide * 2
        th_h = tw * 9 / 16
        lo, hi = int(self.pos - 7), int(self.pos + 8)
        gap_i, gap_v = (self.gap[0], self.gap[1].value(now)) if self.gap else (0, 0.0)
        for j in range(max(0, lo), min(len(self.view), hi + 2)):
            d = j - self.pos + (gap_v if j >= gap_i else 0)
            near = clamp(1 - abs(d))
            sc = 1 + 0.22 * near  # the selected one is bigger and raised
            w_, h_ = tw * sc, th_h * sc
            x_ = W / 2 + d * (tw + gap) - w_ / 2
            y_ = fy - h_ / 2 - 8 * near
            if x_ > W or x_ + w_ < 0:
                continue
            a = ui * clamp(1 - 0.13 * abs(d), 0.3, 1)  # neighbours fade with distance
            idx = self.view[j]
            src = self.get("thumb", idx)
            if near > 0.01:  # accent glow
                for i in range(4):
                    rrect(cr, x_ - 2 - i * 2.5, y_ - 2 - i * 2.5, w_ + 4 + i * 5, h_ + 4 + i * 5, 10 + i * 2.5)
                    cr.set_source_rgba(*acc, 0.12 * near * a)
                    cr.fill()
            cr.save()
            rrect(cr, x_, y_, w_, h_, 8)
            cr.clip()
            cr.set_source_rgba(*s1, a)
            cr.paint()
            if src is not None:
                fade = clamp((now - self.loaded_at.get(("thumb", idx), 0)) / 0.25)
                paint_scaled(cr, src, x_, y_, w_, h_, a * fade, cairo.FILTER_GOOD)
            cr.restore()
            if near > 0.01:
                rrect(cr, x_ - 1, y_ - 1, w_ + 2, h_ + 2, 9)
                cr.set_source_rgba(*acc, near * a)
                cr.set_line_width(2.5)
                cr.stroke()


def draw_mock(cr, th, a, W, H, style=None):
    """The desktop as it will look, at real size (the card scales it down): the islands top bar,
    a file manager with accent folders, a terminal with all 16 colours, a widget, the floating dock."""
    acc, fg, muted, bg, s1, s2 = th["accent"], th["fg"], th["muted"], th["bg"], th["surface"], th["surface2"]

    barstyles.draw_bar(cr, th, style or barstyles.get(None), W, a, text=text, now=time.time())

    def window(x, y, w, h, title):
        shadow(cr, x, y, w, h, 12, 0.08 * a, steps=4, spread=2, drop=6)
        rrect(cr, x, y, w, h, 12)
        cr.set_source_rgba(*bg, 0.97 * a)
        cr.fill()
        cr.save()
        rrect(cr, x, y, w, h, 12)
        cr.clip()
        cr.rectangle(x, y, w, 40)
        cr.set_source_rgba(*s1, a)
        cr.fill()
        cr.rectangle(x, y + 40, w, 1)
        cr.set_source_rgba(*acc, 0.6 * a)
        cr.fill()
        cr.restore()
        text(cr, title, x + w / 2, y + 11, 14, fg, a, "Bold", align="center")
        cr.arc(x + w - 22, y + 20, 9, 0, 2 * math.pi)
        cr.set_source_rgba(*s2, a)
        cr.fill()

    fx, fy, fw, fh = W * 0.06, H * 0.13, W * 0.42, H * 0.5  # file manager
    window(fx, fy, fw, fh, "Files")
    side = fw * 0.28
    cr.rectangle(fx, fy + 41, side, fh - 52)
    cr.set_source_rgba(*s1, 0.7 * a)
    cr.fill()
    for i, lab in enumerate(("Home", "Desktop", "Documents", "Downloads", "Pictures", "Music")):
        yy = fy + 56 + i * 32
        if i == 4:
            rrect(cr, fx + 8, yy - 5, side - 16, 28, 7)
            cr.set_source_rgba(*acc, a)
            cr.fill()
        text(cr, lab, fx + 22, yy, 13, th["on_accent"] if i == 4 else fg, a, width=side - 30)
    cols = 4
    cell = (fw - side - 30) / cols
    for i in range(8):
        gx, gy = fx + side + 20 + (i % cols) * cell, fy + 60 + (i // cols) * (cell * 0.95)
        fwid = cell * 0.62
        rrect(cr, gx + (cell - fwid) / 2, gy, fwid * 0.45, fwid * 0.2, 3)
        cr.set_source_rgba(*acc, 0.75 * a)
        cr.fill()
        rrect(cr, gx + (cell - fwid) / 2, gy + fwid * 0.12, fwid, fwid * 0.72, 5)
        cr.set_source_rgba(*acc, a)
        cr.fill()
        text(cr, ("Music", "Videos", "Pictures", "Public", "Projects", "Templates", "walls", "Documents")[i],
             gx + cell / 2, gy + fwid * 0.9, 12, fg, a, align="center", width=cell - 6)

    tx, ty, tw, tht = W * 0.52, H * 0.34, W * 0.42, H * 0.42  # terminal
    window(tx, ty, tw, tht, "Terminal")
    lh = 21
    lx, ly = tx + 18, ty + 54
    text(cr, "~", lx, ly, 14, muted, a, kind="mono")
    text(cr, "❯", lx + 18, ly, 14, acc, a, kind="mono")
    text(cr, "wallrice status", lx + 38, ly, 14, fg, a, kind="mono")
    rows = (("wallpaper", "the one on show", 4), ("accent", rgb2hex(acc), 5), ("contrast", "7:1 text, 3:1 accent", 2),
            ("terminals", "16 colours, all readable", 6))
    for i, (lab, val, col) in enumerate(rows):
        yy = ly + lh * (i + 1.3)
        text(cr, "●", lx, yy, 13, th["term"][col], a, kind="mono")
        text(cr, lab, lx + 20, yy, 14, fg, a, kind="mono")
        text(cr, val, lx + 140, yy, 14, muted, a, kind="mono")
    bw = (tw - 36) / 8
    for i in range(16):
        cr.rectangle(lx + (i % 8) * bw, ly + lh * 6.2 + (i // 8) * 16, bw - 3, 13)
        cr.set_source_rgba(*th["term"][i], a)
        cr.fill()
    text(cr, "~", lx, ly + lh * 7.9, 14, muted, a, kind="mono")
    text(cr, "❯", lx + 18, ly + lh * 7.9, 14, acc, a, kind="mono")
    cr.rectangle(lx + 38, ly + lh * 7.9 + 2, 9, 17)
    cr.set_source_rgba(*acc, a)
    cr.fill()

    kx, ky, kw, kh = W - 262, 130, 236, 150  # a system widget
    rrect(cr, kx, ky, kw, kh, 10)
    cr.set_source_rgba(*s1, 0.85 * a)
    cr.fill()
    text(cr, "SYSTEM", kx + 12, ky + 8, 13, acc, a, kind="mono")
    cr.rectangle(kx + 80, ky + 17, kw - 94, 1)
    cr.set_source_rgba(*muted, a)
    cr.fill()
    text(cr, "CPU", kx + 12, ky + 30, 13, fg, a, kind="mono")
    text(cr, "9%", kx + kw - 12, ky + 30, 13, fg, a, kind="mono", align="right")
    cr.move_to(kx + 12, ky + 76)
    for i in range(40):
        cr.line_to(kx + 12 + i * (kw - 24) / 39, ky + 76 - 14 * abs(math.sin(i * 0.7)) * (0.4 + 0.6 * (i % 5 == 0)))
    cr.set_source_rgba(*acc, a)
    cr.set_line_width(1.5)
    cr.stroke()
    for i, (lab, val) in enumerate((("RAM", "3.1 / 15.5 GiB"), ("Disk", "64 / 475 GiB"))):
        text(cr, lab, kx + 12, ky + 88 + i * 20, 13, fg, a, kind="mono")
        text(cr, val, kx + kw - 12, ky + 88 + i * 20, 13, fg, a, kind="mono", align="right")

    dw, dh = 470, 54  # the floating dock: rounded, dark, flat monochrome icons
    dx, dy = (W - dw) / 2, H - dh - 10
    rrect(cr, dx, dy, dw, dh, 18)
    cr.set_source_rgba(*bg, 0.9 * a)
    cr.fill_preserve()
    cr.set_source_rgba(*acc, 0.55 * a)
    cr.set_line_width(1)
    cr.stroke()
    for i in range(9):
        cx = dx + 35 + i * (dw - 70) / 8
        rrect(cr, cx - 15, dy + 11, 30, 30, 8)
        cr.set_source_rgba(*fg, 0.88 * a)
        cr.fill()
        if i in (0, 2, 5):  # running dots in the accent
            cr.arc(cx, dy + dh - 6, 2.2, 0, 2 * math.pi)
            cr.set_source_rgba(*acc, a)
            cr.fill()


class PickerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Wallpapers")
        st = load_state()
        W, H, scale = screen_size()
        env = detect.detect()
        cur = st.get("wallpaper")
        if not cur or not Path(cur).is_file():
            cur = backends.get(env).current_wallpaper()
        items = collections.wallpapers(st.get("mode", "all"))
        if cur and Path(cur).is_file() and Path(cur) not in items:
            items.insert(0, Path(cur))  # the picture on show is always in the list, so the opening lands on it
        self.view = PickerView(W, H, scale, items, cur, st.get("mode", "all"),
                               st.get("animations", True) and not st.get("paused"))
        v = self.view
        if v.current:  # the first frame must already be the wallpaper, exactly as the desktop shows it
            try:
                v.set_current(cover(v.current, W, H, scale), theme_of(v.current))
            except Exception:  # noqa: BLE001
                v.set_current(None, None)
        elif v.items:
            v.select(v.sel, fade=False)
        self.closing, self.wake = False, threading.Event()
        self.set_default_size(W, H)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_skip_taskbar_hint(True)
        self.fullscreen()
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.KEY_RELEASE_MASK | Gdk.EventMask.SCROLL_MASK
                        | Gdk.EventMask.SMOOTH_SCROLL_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("draw", lambda _w, cr: self.view.draw(cr, time.monotonic()) or True)
        self.connect("key-press-event", self.on_key)
        self.connect("key-release-event", lambda _w, ev: self.view.guard.release(ev.keyval) or True)
        self.connect("scroll-event", self.on_scroll)
        self.connect("button-press-event", self.on_click)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("map-event", self.on_map)
        self.connect("delete-event", lambda *a: self.quit(1) or True)
        threading.Thread(target=self.loader, daemon=True).start()
        self.add_tick_callback(self.tick)

    def on_map(self, *_):
        display = Gdk.Display.get_default()
        if type(display).__name__.startswith("X11"):  # Wayland: window focus, no global keyboard grab
            GLib.timeout_add(80, lambda: display.get_default_seat().grab(
                self.get_window(), Gdk.SeatCapabilities.KEYBOARD, False, None, None, None) and False)

    def loader(self):
        """One background thread pulls jobs by priority; results come back on the main loop."""
        while not self.closing:
            job = self.view.next_job()
            if job is None:
                self.wake.wait(0.3)
                self.wake.clear()
                continue
            res = self.view.compute(*job)
            GLib.idle_add(self.loaded, job, res)

    def loaded(self, job, res):
        self.view.loaded(job[0], job[1], res)
        self.queue_draw()
        return False

    def poke(self):
        self.wake.set()
        self.queue_draw()

    def confirm(self, path=None):
        path = path or self.view.start_confirm()
        if path is None:
            return
        self.poke()

        def work():
            try:
                ctx = engine.apply(path, effect="none", quiet=True)
                code, settle = 0, ctx.settle
                for note in ctx.notes:
                    print(f"wallrice: {note}", file=sys.stderr)
            except Exception as e:  # noqa: BLE001
                print(f"wallrice: {e}", file=sys.stderr)
                code, settle = 2, 0.0
            GLib.idle_add(self.view.applied, code, settle)
        threading.Thread(target=work, daemon=True).start()

    def on_key(self, _w, ev):
        v = self.view
        if v.phase not in ("open", "browse"):
            return True
        k = Gdk.keyval_name(ev.keyval) or ""
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        fresh = v.guard.press(ev.keyval, ev.time)
        if k in ("Delete", "KP_Delete") or (ctrl and k in ("z", "Z")):
            if fresh:  # a held key (auto-repeat) acts once
                v.remove_selected() if k in ("Delete", "KP_Delete") else v.undo_remove()
        elif k in MOVES:  # arrows repeat on purpose: fast browsing
            v.select(v.sel + MOVES[k])
        elif k == "Home":
            v.select(0)
        elif k == "End":
            v.select(len(v.view) - 1)
        elif k in ("Return", "KP_Enter"):
            self.confirm()
        elif k == "Escape":
            path = v.escape()
            if path:
                self.confirm(path)
        elif k == "BackSpace":
            v.set_query(v.query[:-1])
        elif k == "Tab":
            v.toggle_mock()
        elif ctrl and k in ("u", "U"):
            v.set_query("")
        else:
            cp = Gdk.keyval_to_unicode(ev.keyval)
            ch = chr(cp) if cp else ""
            if ch and ch.isprintable() and not ctrl:
                v.set_query(v.query + ch)
        self.poke()
        return True

    def on_motion(self, _w, ev):
        hover = self.view.over_remove(ev.x, ev.y)
        if hover != self.view.hover_remove:
            self.view.hover_remove = hover
            self.queue_draw()
        return False

    def on_scroll(self, _w, ev):
        if self.view.phase == "browse":
            d = {Gdk.ScrollDirection.UP: -1, Gdk.ScrollDirection.LEFT: -1, Gdk.ScrollDirection.DOWN: 1,
                 Gdk.ScrollDirection.RIGHT: 1}.get(ev.direction)
            if d is None:
                ok, dx, dy = ev.get_scroll_deltas()
                d = (1 if dx + dy > 0 else -1) if ok and abs(dx + dy) > 0.3 else 0
            if d:
                self.view.select(self.view.sel + d)
                self.poke()
        return True

    def on_click(self, _w, ev):
        what = self.view.click(ev.x, ev.y)
        if what == "remove":
            self.view.remove_selected()
        elif what == "confirm":
            self.confirm()
        self.poke()
        return True

    def tick(self, _widget, _clock):
        busy, code = self.view.tick(time.monotonic())
        if code is not None:
            self.quit(code)
            return False
        if busy:
            self.queue_draw()
        return True

    def quit(self, code=None):
        if code is not None:
            self.view.exit_code = code
        self.closing = True
        self.wake.set()
        Gtk.main_quit()
        return True


def main():
    if Gdk.Display.get_default() is None:
        print("wallrice: the picker needs a graphical session", file=sys.stderr)
        return 1
    GLib.set_prgname("wallrice-picker")  # the Wayland app id / X11 class the Shell extension knows
    win = PickerWindow()
    win.show_all()
    Gtk.main()
    if win.view.removed:  # wallpapers removed with Delete leave the disk now, once the picker is gone
        win.hide()
        while Gtk.events_pending():
            Gtk.main_iteration()
        try:
            collections.apply_review()
        except Exception as e:  # noqa: BLE001
            print(f"wallrice: {e}", file=sys.stderr)
    return 0 if win.view.exit_code in (0, 1) else win.view.exit_code
