"""`wallrice doctor`: what was detected, which pieces are active, and what's missing (with the
package to install on this distro)."""
import importlib.util
from pathlib import Path

from . import backends, collections, paths
from .detect import detect
from .render import data_dirs, find_dir, terminals, apps
from .sh import run
from .state import load_state

OK, WARN, INFO = "✓", "✗", "·"


def module_ok(name, gi_version=None):
    if importlib.util.find_spec(name) is None:
        return False
    if gi_version:
        try:
            import gi
            gi.require_version("Gtk", gi_version)
            from gi.repository import Gtk  # noqa: F401
        except (ImportError, ValueError):
            return False
    return True


def icon_caches():
    """Icon themes without icon-theme.cache make every GTK program index them itself (tens of MB of
    RAM each). Returns the themes missing one."""
    missing = []
    for d in data_dirs():
        base = d / "icons"
        if not base.is_dir():
            continue
        for t in sorted(base.iterdir()):
            index = t / "index.theme"
            if not index.is_file() or (t / "icon-theme.cache").is_file() or t.name == "default":
                continue
            try:  # cursor-only themes have no icon directories, so nothing to cache
                has_dirs = any(l.startswith("Directories=") and l.strip() != "Directories="
                               for l in index.read_text(errors="replace").splitlines())
            except OSError:
                has_dirs = False
            if has_dirs:
                missing.append(t)
    return missing


def report(env=None, say=print):
    env = env or detect()
    be = backends.get(env)
    st = load_state()
    lines = []

    def line(mark, text):
        lines.append(f"  {mark} {text}")

    say(f"wallrice doctor: {env.describe()}")
    say(f"backend: {be.name}" + ("" if be.name != "generic" else " (this desktop isn't supported yet: colour files only)"))
    for k, v in be.features.items():
        line(OK if v else WARN, f"{k}: {v or 'not on this desktop yet'}")
    for ok, text in be.doctor():
        line(OK if ok else (INFO if ok is None else WARN), text)

    hint = lambda name: f"  (install: {' '.join(env.packages(name))})" if env.packages(name) else ""  # noqa: E731
    line(OK if module_ok("PIL") else WARN, "Pillow" + ("" if module_ok("PIL") else " missing: no palettes, no picker" + hint("pillow")))
    gtk_ok = module_ok("gi", "3.0") and module_ok("cairo")
    line(OK if gtk_ok else WARN, "GTK 3 + cairo for the picker and the review" +
         ("" if gtk_ok else " missing: the picker falls back to rofi/fzf" + hint("pygobject")))
    line(OK if env.has("wallust") else INFO, "palette: " + ("wallust" if env.has("wallust") else "built-in extractor (wallust not installed; that's fine)"))
    pap = find_dir("icons", "Papirus")
    line(OK if pap else INFO, "Papirus " + ("found: folders follow the accent" if pap else "not installed: folder colours skipped" + hint("papirus")))
    missing = icon_caches()
    if missing:
        line(WARN, f"{len(missing)} icon theme(s) without icon-theme.cache (each GTK app indexes them itself, "
                   f"using RAM): {', '.join(t.name for t in missing[:5])}. Fix: sudo gtk-update-icon-cache -f <dir>")
    else:
        line(OK, "every icon theme has an icon cache")
    line(OK if env.has("git") else WARN, "git " + ("found" if env.has("git") else "missing: git collections can't download" + hint("git")))

    for name, (conf, include) in {**terminals.INCLUDES, **apps.INCLUDES}.items():
        if not env.has(name):
            continue
        main = paths.config_home() / conf
        text = main.read_text(errors="replace") if main.is_file() else ""
        if include.splitlines()[-1].strip() in text:
            line(OK, f"{name} uses the wallrice colours")
        else:
            line(INFO, f"{name}: to use the colours, add to ~/.config/{conf}:  {include}")

    rc, _ = run("systemctl", "--user", "is-active", "wallrice-rotate.timer")
    minutes = st.get("rotate_minutes") or 0
    line(OK if rc == 0 else INFO, f"rotation: {'every ' + str(minutes) + ' min' if rc == 0 else 'off'}"
         + (" (paused)" if st.get("paused") else ""))
    from . import parts
    off = [p.name for p in parts.PARTS if not parts.is_on(st, p)]
    line(INFO, f"mode {st.get('mode', 'all')} · parts off: {', '.join(off) if off else 'none'}  (wallrice parts)")
    pics = collections.all_pictures()
    line(OK if pics else INFO, f"{len(pics)} wallpapers in {paths.walls()}" + ("" if pics else ": run  wallrice walls update"))
    cur = st.get("wallpaper")
    line(OK if cur and Path(cur).is_file() else INFO, f"current wallpaper: {cur or 'none applied yet'}")
    for l in lines:
        say(l)
    return 0
