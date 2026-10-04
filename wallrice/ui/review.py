"""`wallrice walls review`: every picture not reviewed yet, one at a time and whole (fitted, never
cropped) on a blurred copy of itself, with big Remove / Keep buttons. Each choice is saved at once
(Esc stops; the next run carries on where this one stopped). Removed pictures leave the disk when
the review ends, and stay gone after updates.

Keys: → or Y keep, ← or N remove, Backspace undo, Esc stop. Key auto-repeat never makes a choice."""
import sys
import threading
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
import cairo  # noqa: E402
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import collections, engine  # noqa: E402
from ..state import load_review, load_state, save_review  # noqa: E402
from .common import (THEME, KeyGuard, Tween, blurred, contain, ease_in_out, paint_scaled, pretty,  # noqa: E402
                     rrect, screen_size, shadow, size_of, text)

KEEP_KEYS = ("Right", "y", "Y", "k", "K", "Return", "KP_Enter")
REMOVE_KEYS = ("Left", "n", "N", "d", "D", "Delete")
UNDO_KEYS = ("BackSpace", "u", "U")
STOP_KEYS = ("Escape", "q", "Q")


class ReviewView:
    """The review's state, choices and drawing, without a window (tests and offscreen frames use it)."""

    def __init__(self, W, H, scale=1, pics=None):
        self.W, self.H, self.scale = W, H, scale
        self.mw, self.mh = int(W * 0.84), int(H * 0.6)  # the largest a picture is shown
        self.review = load_review()
        pics = collections.all_pictures() if pics is None else pics
        self.queue = [p for p in pics if collections.rel(p) not in self.review["keep"]]
        self.total, self.before = len(pics), len(pics) - len(self.queue)
        self.i, self.history, self.kept, self.removed = 0, [], 0, 0
        self.cache, self.blurs, self.lock = {}, {}, threading.Lock()
        self.leaving = []  # cards on their way out: {"src", "rect", "kind", "tw"}
        self.enter_tw = Tween(0, 1, 0.45)
        self.backs, self.flash, self.buttons, self.hover = [], {}, {}, None
        self.phase, self.message = "review", ""
        self.guard = KeyGuard(gap=0.2)

    # ---------------------------------------------------------------- loading (the next 3 preloaded)

    def wanted(self):
        with self.lock:
            return [j for j in range(self.i, min(self.i + 4, len(self.queue))) if j not in self.cache]

    def load(self, j):
        path = self.queue[j]
        try:
            return contain(path, self.mw, self.mh, self.scale), blurred(path, self.W, self.H)
        except Exception:  # noqa: BLE001 - unreadable: only its name shows
            return (None, (0, 0)), None

    def loaded(self, j, res, blur, now=None):
        with self.lock:
            self.cache[j], self.blurs[j] = res, blur
            for k in [k for k in self.cache if k < self.i - 3]:
                self.cache.pop(k, None)
                self.blurs.pop(k, None)
        if j == self.i:
            self.enter_tw = Tween(0, 1, 0.35, now=now)
            self.push_back(now)

    def push_back(self, now=None):
        b = self.blurs.get(self.i)
        if b is not None:
            self.backs.append({"src": b, "tw": Tween(0, 1, 0.5, now=now)})

    def card_rect(self, j):
        src = self.cache.get(j, (None, None))[0]
        w, h = size_of(src) if src is not None else (self.mw * 0.5, self.mh * 0.5)
        return (self.W - w) / 2, self.H * 0.11 + (self.mh - h) / 2, w, h

    # ---------------------------------------------------------------- choices

    def decide(self, kind, now=None):
        """kind: "keep" or "remove". Saved at once: a crash or Esc loses nothing."""
        now = time.monotonic() if now is None else now
        if self.phase != "review" or self.i >= len(self.queue) or not self.guard.act(now):
            return False
        rel = collections.rel(self.queue[self.i])
        (self.review["keep"] if kind == "keep" else self.review["drop"]).add(rel)
        save_review(self.review)
        self.history.append((self.i, kind))
        self.kept += kind == "keep"
        self.removed += kind == "remove"
        src = self.cache.get(self.i, (None, None))[0]
        if src is not None:
            self.leaving.append({"src": src, "rect": self.card_rect(self.i), "kind": kind,
                                 "tw": Tween(0, 1, 0.42, ease_in_out, now=now)})
        self.flash[kind] = Tween(1, 0, 0.35, now=now)
        self.i += 1
        self.enter_tw = Tween(0, 1, 0.38, now=now)
        self.push_back(now)
        return True

    def undo(self, now=None):
        if self.phase != "review" or not self.history:
            return False
        j, kind = self.history.pop()
        self.review["keep" if kind == "keep" else "drop"].discard(collections.rel(self.queue[j]))
        save_review(self.review)
        self.kept -= kind == "keep"
        self.removed -= kind == "remove"
        self.i, self.leaving = j, []
        self.enter_tw = Tween(0, 1, 0.38, now=now)
        self.push_back(now)
        return True

    @property
    def finished(self):
        return self.i >= len(self.queue)

    # ---------------------------------------------------------------- animation state

    def busy(self, now):
        self.leaving = [c for c in self.leaving if not c["tw"].done(now)]
        while len(self.backs) > 1 and self.backs[1]["tw"].done(now):
            self.backs.pop(0)
        return bool(self.leaving or not self.enter_tw.done(now) or any(not b["tw"].done(now) for b in self.backs)
                    or any(not t.done(now) for t in self.flash.values()) or self.phase == "closing")

    def hit(self, x, y):
        return next((k for k, (bx, by, bw, bh) in self.buttons.items() if bx <= x <= bx + bw and by <= y <= by + bh), None)

    # ---------------------------------------------------------------- drawing

    def button(self, cr, kind, label, x, y, w, h, col, filled, now):
        self.buttons[kind] = (x, y, w, h)
        fl = self.flash[kind].value(now) if kind in self.flash else 0.0
        rrect(cr, x, y, w, h, h / 2)
        cr.set_source_rgba(*col, min(1.0, (0.9 if filled else 0.14) + (0.1 if self.hover == kind else 0) + 0.35 * fl))
        cr.fill_preserve()
        cr.set_source_rgba(*col, 1.0)
        cr.set_line_width(2)
        cr.stroke()
        text(cr, label, x + w / 2, y + h / 2 - h * 0.27, h * 0.36, (1, 1, 1) if filled else col, 1.0, "Bold", align="center")

    def draw(self, cr, now):
        W, H, th = self.W, self.H, THEME
        cr.set_source_rgb(*th["bg"])
        cr.paint()
        for b in self.backs:
            paint_scaled(cr, b["src"], 0, 0, W, H, b["tw"].value(now) * 0.9, cairo.FILTER_GOOD)
        cr.set_source_rgba(*th["bg"], 0.68)
        cr.paint()
        self.buttons = {}
        reviewed = self.before + self.i
        text(cr, "Review wallpapers", W * 0.08, H * 0.03, H * 0.03, th["fg"], 1, "Bold")
        text(cr, f"{reviewed} of {self.total} reviewed  ·  {self.removed} removed this time", W * 0.92, H * 0.037,
             H * 0.018, th["muted"], 1, align="right")
        rrect(cr, W * 0.08, H * 0.085, W * 0.84, 4, 2)
        cr.set_source_rgba(*th["fg"], 0.12)
        cr.fill()
        if self.total:
            rrect(cr, W * 0.08, H * 0.085, max(4, W * 0.84 * reviewed / self.total), 4, 2)
            cr.set_source_rgba(*th["keep"], 1)
            cr.fill()
        if not self.queue:
            msg = ("Nothing to review: every picture has been kept already." if self.total else
                   "No wallpapers yet: run  wallrice walls update")
            text(cr, msg, W / 2, H * 0.45, H * 0.026, th["fg"], 1, align="center")
            if self.phase == "review":
                self.button(cr, "stop", "Close", W / 2 - W * 0.08, H * 0.82, W * 0.16, H * 0.065, th["keep"], True, now)
            return
        for c in self.leaving:  # kept cards fly up and to the right, removed ones drop away tinted red
            t = c["tw"].value(now)
            x, y, w, h = c["rect"]
            dx, dy, rot = (W * 0.32, -H * 0.18, 0.12) if c["kind"] == "keep" else (-W * 0.05, H * 0.55, -0.16)
            cr.save()
            cr.translate(x + w / 2 + dx * t, y + h / 2 + dy * t)
            cr.rotate(rot * t)
            cr.scale(1 - 0.15 * t, 1 - 0.15 * t)
            rrect(cr, -w / 2, -h / 2, w, h, 14)
            cr.clip()
            paint_scaled(cr, c["src"], -w / 2, -h / 2, w, h, 1 - t)
            if c["kind"] == "remove":
                cr.set_source_rgba(*th["remove"], 0.45 * (1 - t))
                cr.paint()
            cr.restore()
        if self.i < len(self.queue):
            path = self.queue[self.i]
            src, size = self.cache.get(self.i, (None, (0, 0)))
            x, y, w, h = self.card_rect(self.i)
            e = self.enter_tw.value(now)
            if src is not None:
                sc = 0.92 + 0.08 * e
                cr.save()
                cr.translate(x + w / 2, y + h / 2)
                cr.scale(sc, sc)
                shadow(cr, -w / 2, -h / 2, w, h, 14, 0.06 * e, drop=12)
                rrect(cr, -w / 2, -h / 2, w, h, 14)
                cr.clip()
                paint_scaled(cr, src, -w / 2, -h / 2, w, h, e, cairo.FILTER_GOOD)
                cr.restore()
            else:
                text(cr, "Loading …", W / 2, H * 0.38, H * 0.022, th["muted"], 1, align="center")
            label, title = pretty(path)
            credit = collections.describe(path)[3]
            iy = H * 0.11 + self.mh + H * 0.02
            text(cr, label.upper(), W / 2, iy, H * 0.015, th["keep"], 1, "Bold", align="center")
            text(cr, title, W / 2, iy + H * 0.024, H * 0.024, th["fg"], 1, align="center", width=W * 0.8)
            sub = "  ·  ".join(s for s in (f"{size[0]} × {size[1]}" if size[0] else "", credit) if s)
            text(cr, sub, W / 2, iy + H * 0.06, H * 0.015, th["muted"], 1, align="center", width=W * 0.84)
        if self.phase == "review":
            bw, bh, by = W * 0.17, H * 0.068, H * 0.855
            self.button(cr, "remove", "✕   Remove", W / 2 - bw - W * 0.015, by, bw, bh, th["remove"], False, now)
            self.button(cr, "keep", "✓   Keep", W / 2 + W * 0.015, by, bw, bh, th["keep"], True, now)
            if self.history:
                self.button(cr, "undo", "Undo", W * 0.08, by + bh * 0.2, W * 0.07, bh * 0.6, th["muted"], False, now)
            self.button(cr, "stop", "Stop", W * 0.85, by + bh * 0.2, W * 0.07, bh * 0.6, th["muted"], False, now)
            text(cr, "←  or  N   remove        →  or  Y   keep        Backspace   undo        Esc   stop (choices are saved)",
                 W / 2, H * 0.95, H * 0.015, th["muted"], 0.9, align="center")
        else:
            text(cr, self.message, W / 2, H * 0.875, H * 0.022, th["fg"], 1, align="center")


def finish_work():
    """Take the removed pictures off the disk, and move off a removed current wallpaper."""
    collections.apply_review()
    st = load_state()
    cur = st.get("wallpaper")
    if cur and not Path(cur).is_file():
        img = collections.pick_random(st.get("mode", "all"))
        if img:
            engine.apply(img, quiet=True)


class ReviewWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Review wallpapers")
        W, H, scale = screen_size()
        self.view = ReviewView(W, H, scale)
        self.closing, self.wake = False, threading.Event()
        self.set_default_size(W, H)
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.fullscreen()
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.KEY_RELEASE_MASK | Gdk.EventMask.BUTTON_PRESS_MASK
                        | Gdk.EventMask.POINTER_MOTION_MASK)
        self.connect("draw", lambda _w, cr: self.view.draw(cr, time.monotonic()) or True)
        self.connect("key-press-event", self.on_key)
        self.connect("key-release-event", lambda _w, ev: self.view.guard.release(ev.keyval) or True)
        self.connect("button-press-event", self.on_click)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("map-event", self.on_map)
        self.connect("delete-event", lambda *a: self.finish() or True)
        self.connect("configure-event", self.on_configure)
        threading.Thread(target=self.loader, daemon=True).start()
        self.add_tick_callback(self.tick)

    def on_map(self, *_):
        display = Gdk.Display.get_default()
        if type(display).__name__.startswith("X11"):  # Wayland: focus is enough, there's no global grab
            GLib.timeout_add(80, lambda: display.get_default_seat().grab(
                self.get_window(), Gdk.SeatCapabilities.KEYBOARD, False, None, None, None) and False)

    def on_configure(self, _w, ev):
        if (ev.width, ev.height) != (self.view.W, self.view.H) and ev.width > 200:
            v = self.view
            v.W, v.H = ev.width, ev.height
            v.mw, v.mh = int(v.W * 0.84), int(v.H * 0.6)
            with v.lock:
                v.cache.clear()
                v.blurs.clear()
            self.wake.set()
        return False

    def loader(self):
        while not self.closing:
            todo = self.view.wanted()
            if not todo:
                self.wake.wait(0.3)
                self.wake.clear()
                continue
            j = todo[0]
            res, blur = self.view.load(j)
            GLib.idle_add(self.loaded, j, res, blur)
            time.sleep(0.001)

    def loaded(self, j, res, blur):
        self.view.loaded(j, res, blur)
        self.queue_draw()
        return False

    def act(self, what):
        v = self.view
        done = {"keep": lambda: v.decide("keep"), "remove": lambda: v.decide("remove"), "undo": v.undo,
                "stop": self.finish}[what]()
        self.wake.set()
        if v.finished and v.phase == "review":
            self.finish()
        self.queue_draw()
        return done

    def on_key(self, _w, ev):
        v = self.view
        if not v.guard.press(ev.keyval, ev.time):
            return True  # auto-repeat of a key that's still down
        k = Gdk.keyval_name(ev.keyval)
        if v.phase == "done":
            self.quit()
        elif k in KEEP_KEYS:
            self.act("keep")
        elif k in REMOVE_KEYS:
            self.act("remove")
        elif k in UNDO_KEYS or (k in ("z", "Z") and ev.state & Gdk.ModifierType.CONTROL_MASK):
            self.act("undo")
        elif k in STOP_KEYS:
            self.finish()
        return True

    def on_click(self, _w, ev):
        if self.view.phase == "done":
            self.quit()
            return True
        kind = self.view.hit(ev.x, ev.y)
        if kind:
            self.act(kind)
        return True

    def on_motion(self, _w, ev):
        hover = self.view.hit(ev.x, ev.y)
        if hover != self.view.hover:
            self.view.hover = hover
            self.queue_draw()
        return False

    def tick(self, _widget, _clock):
        if self.view.busy(time.monotonic()):
            self.queue_draw()
        return True

    def finish(self):
        """Stop, or all done: take the removed pictures off the disk, then close."""
        v = self.view
        if v.phase != "review":
            return True
        v.phase = "closing"
        v.message = f"Removing {v.removed} picture{'s' if v.removed != 1 else ''} …" if v.removed else "Saving …"

        def work():
            try:
                finish_work()
                msg = "Done."
            except Exception as e:  # noqa: BLE001
                msg = f"Couldn't remove everything: {e}"
            GLib.idle_add(self.closed, msg)
        threading.Thread(target=work, daemon=True).start()
        self.queue_draw()
        return True

    def closed(self, msg):
        v = self.view
        left = len(v.queue) - v.i
        v.message = f"{msg}  Kept {v.kept}, removed {v.removed}" + (f", {left} left for next time." if left else ". All reviewed.")
        v.phase = "done"
        GLib.timeout_add(2500, self.quit)
        self.queue_draw()
        return False

    def quit(self):
        self.closing = True
        self.wake.set()
        Gtk.main_quit()
        return False


def main():
    if Gdk.Display.get_default() is None:
        print("wallrice: the review needs a graphical session", file=sys.stderr)
        return 1
    win = ReviewWindow()
    win.show_all()
    Gtk.main()
    return 0
