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
    settle: float = 0.0       # seconds after apply() returns until the desktop fully shows the picture
    parts: dict = field(default_factory=dict)  # {part: on?} (`wallrice on|off PART`); missing = on
    term_slot: str = "a"      # the A/B copy of the terminal palette not in use

    def on(self, part):
        return self.parts.get(part, True)


class Backend:
    name = "generic"
    # the parts (wallrice.parts) this desktop has; GNOME adds its dock, taskbar icons and top bar
    parts = {"apps", "icons", "terminal", "transitions", "rotation"}
    # what this backend does live, for `wallrice doctor`
    features = {"wallpaper": None, "live colours": None, "transition": None, "Super+W": None}

    def __init__(self, env, run=sh.run):
        self.env = env
        self.run = run

    def read(self, key):
        """A dconf key's current value (GVariant text), or None."""
        rc, out = self.run("dconf", "read", key)
        return out.strip() if rc == 0 and out.strip() else None

    def load(self, keys):
        """Write {"/path/to/key": gvariant_text} in one dconf transaction."""
        sections = {}
        for key, value in keys.items():
            d, k = key.rsplit("/", 1)
            sections.setdefault(d.strip("/"), []).append(f"{k}={value}")
        ini = "".join(f"[{d}]\n" + "\n".join(lines) + "\n\n" for d, lines in sections.items())
        rc, out = self.run("dconf", "load", "/", input=ini)
        if rc != 0:
            raise RuntimeError(f"dconf load failed: {out.strip()[:200]}")

    def finish(self):
        """Wait for anything still animating (a timer job's processes end with the job)."""

    # Terminals, which can be left out of the theme (`wallrice terminal off`)
    def current_term_slot(self):
        """The A/B terminal palette in use, read from the terminal's settings, or None."""
        return None

    def terminal_steps(self, ctx):
        """Live steps that recolour this desktop's own terminal: [(label, callable)]."""
        return []

    def part_of(self, key):
        """The part a backed-up setting belongs to (restored by `wallrice off PART`), or None."""
        if key.startswith("/org/gnome/desktop/interface/"):  # GTK apps' settings, on several desktops
            return "icons" if key.endswith("/icon-theme") else "apps"
        return None

    # Backups: settings are named by keys. dconf keys are paths ("/org/..."); backends with other
    # settings stores use their own prefixes ("xfconf:CHANNEL:PROP", "kde:...") and override these.
    def read_setting(self, key):
        return self.read(key) if key.startswith("/") else None

    def restore_setting(self, key, value):
        if not key.startswith("/"):
            return
        if value is None:
            self.run("dconf", "reset", key)
        else:
            self.run("dconf", "write", key, value)

    def bind_hint(self, binding, command):
        """What to add by hand where wallrice can't set a shortcut itself."""
        return f"add a shortcut in the desktop's keyboard settings: {binding} runs  {command}"

    def autostart_hint(self, command):
        """Desktops that don't run XDG autostart: the line to add to their config, or None."""
        return None

    def current_slot(self):
        """The A/B slot in use right now, read from the desktop, or None."""
        return None

    def current_wallpaper(self):
        """The picture the desktop shows now (before wallrice ran), or None."""
        return None

    def outputs(self, ctx):
        """Extra files this desktop needs: {path: text}. Must not change anything."""
        return {}

    def gtk_css(self, ctx):
        """Extra GTK 3 CSS for this desktop's own GTK widgets (Xfce's panel, notifications)."""
        return ""

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
