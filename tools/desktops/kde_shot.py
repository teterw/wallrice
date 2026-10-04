"""A screenshot of a (test) KWin session: org.kde.KWin.ScreenShot2.CaptureWorkspace writes raw pixels into
a pipe. KWin must run with KWIN_SCREENSHOT_NO_PERMISSION_CHECKS=1 (only in the test container).

  python3 kde_shot.py OUT.png"""
import os
import sys

from gi.repository import Gio, GLib
from PIL import Image

# QImage formats KWin uses, and how Pillow reads them on a little-endian machine
FORMATS = {4: ("RGB", "BGRX"), 5: ("RGBA", "BGRA"), 6: ("RGBA", "BGRa"), 17: ("RGBA", "RGBX"),
           18: ("RGBA", "RGBA"), 19: ("RGBA", "RGBa")}


def main(out):
    r, w = os.pipe()
    fds = Gio.UnixFDList()
    fds.append(w)  # dup'ed: our copy closes now, so the pipe ends when KWin is done
    os.close(w)
    bus = Gio.bus_get_sync(Gio.BusType.SESSION)
    res, _ = bus.call_with_unix_fd_list_sync(
        "org.kde.KWin", "/org/kde/KWin/ScreenShot2", "org.kde.KWin.ScreenShot2", "CaptureWorkspace",
        GLib.Variant("(a{sv}h)", ({}, 0)), GLib.VariantType("(a{sv})"), Gio.DBusCallFlags.NONE, 15000, fds, None)
    del fds
    meta = res.unpack()[0]
    data = b""
    with os.fdopen(r, "rb") as f:
        while chunk := f.read(1 << 20):
            data += chunk
    mode, raw = FORMATS.get(meta.get("format"), ("RGBA", "BGRA"))
    im = Image.frombuffer(mode, (meta["width"], meta["height"]), data, "raw", raw, meta["stride"], 1)
    im.convert("RGB").save(out)


if __name__ == "__main__":
    main(sys.argv[1])
