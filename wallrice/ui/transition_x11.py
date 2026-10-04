"""swww-style wallpaper changes on X11 desktops (Xfce, Cinnamon, MATE, LXQt, i3, bspwm, Openbox).

One window per monitor with the DESKTOP type hint, so it sits above the wallpaper and below every
window. It draws the OLD picture, prints "ready" (the backend then switches the real wallpaper
underneath and recolours halfway), and animates to the NEW one: a soft circle growing from the
pointer, a soft angled wipe, a rippling wave, or a fade (1.35 s, eased). Everything is drawn with
cairo on the CPU, so it works without GPU drivers. On Wayland apps can't place windows at the
desktop layer, so Wayland desktops use their own animations instead (swww, GNOME, Plasma).

  python3 -m wallrice.ui.transition_x11 OLD NEW [grow|wipe|wave|fade|random]"""
import math
import random
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
import cairo  # noqa: E402
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .common import clamp, cover, ease_in_out  # noqa: E402

EFFECTS = ("grow", "wipe", "wave", "fade")


def paint_new(cr, effect, w, h, new, p, origin, angle):
    """Draw the new picture over the old one at progress p (0..1)."""
    cr.save()
    if effect == "fade":
        cr.set_source_surface(new, 0, 0)
        cr.paint_with_alpha(p)
    elif effect == "grow":  # a soft-edged circle from the pointer
        cx, cy = origin
        soft = 0.14 * min(w, h)
        r = p * (max(math.hypot(cx - x, cy - y) for x in (0, w) for y in (0, h)) + soft)
        mask = cairo.RadialGradient(cx, cy, max(0.0, r - soft), cx, cy, max(r, 0.01))
        mask.add_color_stop_rgba(0, 0, 0, 0, 1)
        mask.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.set_source_surface(new, 0, 0)
        cr.mask(mask)
    else:
        dx, dy = math.cos(angle), math.sin(angle)
        proj = [x * dx + y * dy for x in (0, w) for y in (0, h)]
        lo, hi = min(proj), max(proj)
        if effect == "wipe":  # a soft straight edge sweeping across at an angle
            soft = 0.12 * min(w, h)
            s = lo + p * (hi - lo + 2 * soft)
            mask = cairo.LinearGradient(dx * (s - soft), dy * (s - soft), dx * s, dy * s)
            mask.add_color_stop_rgba(0, 0, 0, 0, 1)
            mask.add_color_stop_rgba(1, 0, 0, 0, 0)
            cr.set_source_surface(new, 0, 0)
            cr.mask(mask)
        else:  # wave: a rippling edge sweeping across
            nx, ny = -dy, dx
            amp, lam = 0.04 * min(w, h), 0.25 * max(w, h)
            s = lo - 2 * amp + p * (hi - lo + 4 * amp)
            along = [x * nx + y * ny for x in (0, w) for y in (0, h)]
            a0, a1 = min(along) - lam, max(along) + lam
            n = 96
            for i in range(n + 1):
                u = a0 + (a1 - a0) * i / n
                off = s + amp * math.sin(2 * math.pi * u / lam + p * 7)
                (cr.move_to if i == 0 else cr.line_to)(dx * off + nx * u, dy * off + ny * u)
            back = lo - 4 * amp - 10
            cr.line_to(dx * back + nx * a1, dy * back + ny * a1)
            cr.line_to(dx * back + nx * a0, dy * back + ny * a0)
            cr.close_path()
            cr.clip()
            cr.set_source_surface(new, 0, 0)
            cr.paint()
    cr.restore()


def pick_effect(effect):
    if effect in EFFECTS:
        return effect
    return random.choices(EFFECTS, weights=(4, 3, 3, 1))[0]


class Transition:
    def __init__(self, old, new, effect):
        self.effect = pick_effect(effect)
        self.dur = 1.0 if self.effect == "fade" else 1.35
        self.angle = math.radians(random.choice((15, 165, 195, 345, 60, 240)))
        self.t0, self.announced = None, False
        display = Gdk.Display.get_default()
        try:
            _, px, py = display.get_default_seat().get_pointer().get_position()
        except Exception:  # noqa: BLE001 - no pointer: grow from the middle
            px = py = None
        self.views = []
        for i in range(display.get_n_monitors()):
            mon = display.get_monitor(i)
            g, scale = mon.get_geometry(), mon.get_scale_factor()
            old_s, new_s = cover(old, g.width, g.height, scale), cover(new, g.width, g.height, scale)
            inside = px is not None and g.x <= px < g.x + g.width and g.y <= py < g.y + g.height
            origin = (px - g.x, py - g.y) if inside else (g.width * random.uniform(0.3, 0.7), g.height * random.uniform(0.3, 0.7))
            win = Gtk.Window()
            win.set_type_hint(Gdk.WindowTypeHint.DESKTOP)
            win.set_decorated(False)
            win.set_skip_taskbar_hint(True)
            win.set_skip_pager_hint(True)
            win.set_accept_focus(False)
            win.set_keep_below(True)
            win.set_app_paintable(True)
            win.move(g.x, g.y)
            win.set_size_request(g.width, g.height)
            view = {"win": win, "w": g.width, "h": g.height, "old": old_s, "new": new_s, "origin": origin, "drawn": False}
            win.connect("draw", self.draw, view)
            self.views.append(view)
        for v in self.views:
            v["win"].show_all()
            v["win"].stick()
        self.views[0]["win"].add_tick_callback(self.tick)
        GLib.timeout_add(8000, Gtk.main_quit)  # whatever happens, never stay on screen

    def draw(self, _widget, cr, v):
        p = 0.0 if self.t0 is None else ease_in_out(clamp((time.monotonic() - self.t0) / self.dur))
        cr.set_source_surface(v["old"], 0, 0)
        cr.paint()
        if p > 0:
            paint_new(cr, self.effect, v["w"], v["h"], v["new"], p, v["origin"], self.angle)
        if not v["drawn"]:
            v["drawn"] = True
            if all(x["drawn"] for x in self.views) and not self.announced:
                self.announced = True
                GLib.timeout_add(60, self.announce)
        return True

    def announce(self):
        print("ready", flush=True)  # the backend switches the wallpaper underneath now
        GLib.timeout_add(150, self.start)
        return False

    def start(self):
        self.t0 = time.monotonic()
        return False

    def tick(self, _widget, _clock):
        for v in self.views:
            v["win"].queue_draw()
        if self.t0 is not None and time.monotonic() - self.t0 > self.dur + 0.4:
            Gtk.main_quit()  # the desktop has drawn the new wallpaper underneath by now
            return False
        return True


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if Gdk.Display.get_default() is None:
        return 1
    try:
        Transition(Path(argv[0]), Path(argv[1]), argv[2] if len(argv) > 2 else "random")
    except Exception as e:  # noqa: BLE001 - the change goes on without the animation
        print(f"wallrice: {e}", file=sys.stderr)
        return 1
    Gtk.main()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
