"""`wallrice bar`: choose the top bar's style, with a preview of each one on the current wallpaper.
Moving the selection restyles the real top bar at once (the wallrice Shell extension reloads its
stylesheet), so what you see up there is the real thing. Enter keeps it; Esc puts the old one back.

Keys: ↑ ↓ or 1-9 choose, M dock icons monochrome / colour, Enter keep, Esc cancel."""
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
import cairo  # noqa: E402
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import barstyles, palette  # noqa: E402
from ..backends import gnome  # noqa: E402
from ..state import load_state, update_state  # noqa: E402
from ..theme import derive  # noqa: E402
from .common import Tween, cover, ease_in_out, paint_scaled, rrect, text  # noqa: E402

W, H = 1180, 840
ROW_H, TOP = 66, 112
SCREEN_W = 1920  # previews are the real bar, drawn at a 1920-wide screen's size and scaled down


class ChooserView:
    def __init__(self, st=None, now=None):
        st = st or load_state()
        self.original = barstyles.get(st.get("bar_style"))
        self.sel = barstyles.STYLES.index(self.original)
        self.dock_mono = bool(st.get("dock_mono", True))
        self.original_mono = self.dock_mono
        cur = st.get("wallpaper")
        self.wall = None
        self.theme = None
        if cur and Path(cur).is_file():
            try:
                self.wall = cover(cur, SCREEN_W, SCREEN_W * 9 // 16)
                self.theme = derive(palette.extract(cur))
            except Exception:  # noqa: BLE001
                self.wall = None
        self.theme = self.theme or derive({"background": "#0b0a12", "foreground": "#ece9f4",
                                           **{f"color{i}": "#8b5cf6" for i in range(16)}})
        self.pos_tw = Tween(self.sel, self.sel, 0.01, now=now)
        self.rows = []

    @property
    def style(self):
        return barstyles.STYLES[self.sel]

    def select(self, i, now=None):
        i = max(0, min(len(barstyles.STYLES) - 1, i))
        if i == self.sel:
            return False
        now = time.monotonic() if now is None else now
        self.pos_tw = Tween(self.pos_tw.value(now), i, 0.22, ease_in_out, now=now)
        self.sel = i
        return True

    def row_at(self, x, y):
        for i, (rx, ry, rw, rh) in enumerate(self.rows):
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return i
        return None

    def busy(self, now):
        return not self.pos_tw.done(now)

    def draw(self, cr, now):
        th = self.theme
        bg, fg, acc, muted, s1 = th["bg"], th["fg"], th["accent"], th["muted"], th["surface"]
        cr.set_source_rgb(*bg)
        cr.paint()
        text(cr, "Top bar style", 40, 28, 28, fg, 1, "Bold")
        text(cr, "Your real top bar changes as you choose.   Enter keeps it,  Esc puts the old one back.",
             40, 70, 15, muted, 1)
        self.rows = []
        pw = W - 80
        k = pw / SCREEN_W
        hl = self.pos_tw.value(now)
        y_hl = TOP + hl * ROW_H
        rrect(cr, 30, y_hl - 5, pw + 20, ROW_H, 12)  # the highlight glides between rows
        cr.set_source_rgba(*acc, 0.18)
        cr.fill_preserve()
        cr.set_source_rgba(*acc, 0.9)
        cr.set_line_width(2)
        cr.stroke()
        for i, style in enumerate(barstyles.STYLES):
            y = TOP + i * ROW_H
            self.rows.append((30, y - 5, pw + 20, ROW_H))
            cr.save()
            rrect(cr, 40, y, pw, 40, 8)
            cr.clip()
            if self.wall is not None:
                paint_scaled(cr, self.wall, 40, y, pw, pw * 9 / 16, 1.0, cairo.FILTER_GOOD)
            else:
                cr.set_source_rgba(*s1, 1)
                cr.paint()
            cr.translate(40, y)
            cr.scale(k, k)
            barstyles.draw_bar(cr, th, style, SCREEN_W, 1.0, text=text, now=time.time(), title="Files")
            cr.restore()
            chosen = i == self.sel
            text(cr, barstyles.describe(style), 44, y + 42, 13, acc if chosen else fg, 1, "Bold" if chosen else "")
            if style == self.original:
                text(cr, "current", 40 + pw, y + 42, 12, muted, 1, align="right")
        fy = TOP + len(barstyles.STYLES) * ROW_H + 10
        text(cr, "Dock icons", 40, fy + 6, 15, fg, 1, "Bold")
        for j, (label, on) in enumerate((("Monochrome", True), ("Colour", False))):
            bx = 160 + j * 150
            rrect(cr, bx, fy, 136, 32, 16)
            active = self.dock_mono == on
            cr.set_source_rgba(*(acc if active else s1), 1)
            cr.fill()
            text(cr, label, bx + 68, fy + 7, 14, th["on_accent"] if active else fg, 1, "Bold" if active else "", align="center")
        text(cr, "↑ ↓  or  1–9  choose      M  dock icons      Enter  keep      Esc  cancel", W / 2, H - 34, 13, muted, 1,
             align="center")


class ChooserWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Top bar style")
        self.view = ChooserView()
        self.done = False
        self.set_default_size(W, H)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_app_paintable(True)
        self.add_events(Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
        self.connect("draw", lambda _w, cr: self.view.draw(cr, time.monotonic()) or True)
        self.connect("key-press-event", self.on_key)
        self.connect("button-press-event", self.on_click)
        self.connect("scroll-event", self.on_scroll)
        self.connect("delete-event", lambda *a: self.finish(keep=True) or True)
        self.add_tick_callback(lambda *_: (self.view.busy(time.monotonic()) and self.queue_draw()) or True)
        self.pending = None

    def changed(self):
        """Restyle the real top bar (debounced: arrow keys can repeat quickly)."""
        self.queue_draw()
        if self.pending:
            GLib.source_remove(self.pending)
        self.pending = GLib.timeout_add(90, self.push)

    def push(self):
        self.pending = None
        st = update_state(bar_style=self.view.style.id, dock_mono=self.view.dock_mono)
        gnome.refresh_shell(st)
        return False

    def finish(self, keep):
        if self.done:
            return
        self.done = True
        if self.pending:
            GLib.source_remove(self.pending)
            self.pending = None
        v = self.view
        if not keep:
            st = update_state(bar_style=v.original.id, dock_mono=v.original_mono)
        else:
            st = update_state(bar_style=v.style.id, dock_mono=v.dock_mono)
        gnome.refresh_shell(st)
        print(f"top bar: {barstyles.get(st['bar_style']).name}" + ("" if keep else " (unchanged)"))
        Gtk.main_quit()

    def on_key(self, _w, ev):
        k = Gdk.keyval_name(ev.keyval) or ""
        v = self.view
        if k in ("Down", "Right", "j", "Tab"):
            v.select(v.sel + 1) and self.changed()
        elif k in ("Up", "Left", "k", "ISO_Left_Tab"):
            v.select(v.sel - 1) and self.changed()
        elif k.isdigit() and k != "0":
            v.select(int(k) - 1) and self.changed()
        elif k in ("m", "M"):
            v.dock_mono = not v.dock_mono
            self.changed()
        elif k in ("Return", "KP_Enter", "space"):
            self.finish(keep=True)
        elif k == "Escape":
            self.finish(keep=False)
        return True

    def on_click(self, _w, ev):
        v = self.view
        i = v.row_at(ev.x, ev.y)
        if i is not None:
            if ev.type == Gdk.EventType._2BUTTON_PRESS:
                self.finish(keep=True)
            elif v.select(i):
                self.changed()
            return True
        fy = TOP + len(barstyles.STYLES) * ROW_H + 10
        if fy <= ev.y <= fy + 32 and 160 <= ev.x <= 446:
            v.dock_mono = ev.x < 296
            self.changed()
        return True

    def on_scroll(self, _w, ev):
        d = {Gdk.ScrollDirection.UP: -1, Gdk.ScrollDirection.DOWN: 1}.get(ev.direction, 0)
        if d and self.view.select(self.view.sel + d):
            self.changed()
        return True


def set_style(name, say=print):
    """`wallrice bar STYLE`: set it without the chooser."""
    if name in ("mono", "colour", "color"):
        st = update_state(dock_mono=name == "mono")
    else:
        style = barstyles.get(name)
        if style.id != name and not (name.isdigit() and 1 <= int(name) <= len(barstyles.STYLES)):
            say(f"wallrice: unknown style {name}. Styles: " + ", ".join(
                f"{i + 1} {s.id}" for i, s in enumerate(barstyles.STYLES)))
            return 2
        st = update_state(bar_style=style.id)
    gnome.refresh_shell(st)
    say(f"top bar: {barstyles.get(st['bar_style']).name} · dock icons {'monochrome' if st['dock_mono'] else 'colour'}")
    return 0


def main():
    if Gdk.Display.get_default() is None:
        print("wallrice: the chooser needs a graphical session; use  wallrice bar STYLE", file=sys.stderr)
        return 1
    GLib.set_prgname("wallrice-bar")
    win = ChooserWindow()
    win.show_all()
    Gtk.main()
    return 0

