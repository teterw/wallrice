"""The interface every desktop backend implements. The generic backend is also the fallback for a
desktop wallrice doesn't know yet: it writes the colour files and recolours open terminals, and says
what it couldn't do."""
import ast
from dataclasses import dataclass, field
from pathlib import Path

from .. import sh


@dataclass
class Context:
    img: Path
    theme: dict
    slot: str                 # "a" or "b": the copy of each A/B theme not in use
    env: object
    effect: str = "random"    # transition effect, or "none"
    old: Path = None          # the wallpaper before this one
    icons: dict = None        # the Papirus overlay plan, when Papirus is installed
    notes: list = field(default_factory=list)


class Backend:
    name = "generic"
    # what this backend does live, for `wallrice doctor`
    features = {"wallpaper": None, "live colours": None, "transition": None, "Super+W": None}

    def __init__(self, env, run=sh.run):
        self.env = env
        self.run = run

    def read(self, key):
        """A dconf key's current value (GVariant text), or None."""
        rc, out = self.run("dconf", "read", key)
        return out.strip() if rc == 0 and out.strip() else None

    def current_slot(self):
        """The A/B slot in use right now, read from the desktop, or None."""
        return None

    def current_wallpaper(self):
        """The picture the desktop shows now (before wallrice ran), or None."""
        return None

    def outputs(self, ctx):
        """Extra files this desktop needs: {path: text}. Must not change anything."""
        return {}

    def settings_touched(self, ctx):
        """dconf keys this backend will change (for the backup)."""
        return []

    def set_wallpaper(self, ctx):
        """Show the new wallpaper. Returns how many seconds to wait before recolouring, so the colours
        change halfway through the transition."""
        ctx.notes.append(f"{self.name}: can't set the wallpaper on this desktop yet")
        return 0.0

    def activate(self, ctx):
        """Live recolouring steps after the files are written: [(label, callable)]."""
        return []

    def bind_key(self, binding, command, name):
        return False

    def unbind_keys(self):
        return False

    def doctor(self):
        """[(ok: bool|None, line)] about this backend."""
        return []


def gv_str(s):
    """A GVariant string literal."""
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def gv_list(text):
    """Parse a GVariant string array ("['a', 'b']" or "@as []") into a list."""
    text = (text or "").strip()
    if text.startswith("@as"):
        text = text[3:].strip()
    try:
        v = ast.literal_eval(text) if text else []
    except (ValueError, SyntaxError):
        return []
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else []


def gv_strip(text):
    """'value' -> value for a GVariant string, None for nothing."""
    text = (text or "").strip()
    if len(text) >= 2 and text[0] == text[-1] == "'":
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text[1:-1]
    return text or None
