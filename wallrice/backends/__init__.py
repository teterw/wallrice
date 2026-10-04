"""Desktop backends, chosen by detection (detect.Env.backend)."""
from .base import Backend, Context
from .gnome import Gnome
from .gsettings_desktops import Cinnamon, Mate
from .kde import Kde
from .lxqt import Lxqt
from .wlroots import Wlroots
from .x11wm import X11wm
from .xfce import Xfce

BACKENDS = {"gnome": Gnome, "kde": Kde, "xfce": Xfce, "cinnamon": Cinnamon, "mate": Mate, "lxqt": Lxqt,
            "wlroots": Wlroots, "x11wm": X11wm}


def get(env, run=None):
    cls = BACKENDS.get(env.backend, Backend)
    return cls(env, run) if run else cls(env)


__all__ = ["Backend", "Context", "get", "BACKENDS"]
