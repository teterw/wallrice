"""apply(): one wallpaper -> the whole desktop re-themed.

Everything is worked out and rendered in memory first: if the palette or any renderer fails, nothing
is written and the old theme stays whole (the desktop is never half-themed). Then the files are
written (the A/B copies not in use), the wallpaper is set (its transition starts), and halfway
through the transition the backend switches every app to the fresh copies. Each live step is
best-effort: one that can't run prints one line and the rest go on."""
import json
import shutil
import time
from pathlib import Path

from . import backends, backup, detect, palette, paths
from .color import rgb2hex
from .render import apps, gtk, icons, terminals
from .sh import run
from .state import load_state, update_state, write_atomic
from .theme import derive

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
EFFECTS = ("grow", "wipe", "wave", "fade")


class ApplyError(Exception):
    pass


def other(slot):
    return "b" if slot == "a" else "a"


def render_all(ctx, backend):
    """Every output, in memory: ({path: text}, icon plan). Raises if anything can't be made."""
    th, env, slot = ctx.theme, ctx.env, ctx.slot
    files = {}
    files.update(gtk.outputs(th, slot, extra=backend.gtk_css(ctx)))
    if ctx.terminals:
        files.update(terminals.outputs(th, env, ctx.term_slot))
    files.update(apps.outputs(th, env))
    plan = icons.plan(th["accent"], slot)
    if plan:
        files.update(plan["files"])
    files.update(backend.outputs(ctx))
    return files, plan


def write_icons(plan, run=run):
    root = plan["root"]
    keep = set(plan["files"])
    if root.is_dir():  # the copy not in use: rebuild it from scratch
        for p in sorted(root.rglob("*"), reverse=True):
            if p in keep:
                continue
            if p.is_symlink() or p.is_file():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
    for link, target in plan["links"].items():
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
    if shutil.which("gtk-update-icon-cache"):
        run("gtk-update-icon-cache", "-f", "-q", str(root))


def apply(img, effect="random", quiet=False, env=None, backend=None):
    img = Path(img).expanduser().resolve()
    if not img.is_file() or img.suffix.lower() not in IMAGE_EXT:
        raise ApplyError(f"not an image: {img}")
    env = env or detect.detect()
    backend = backend or backends.get(env)
    state = load_state()
    if state.get("paused") or not state.get("animations", True):
        effect = "none"
    old = Path(state["wallpaper"]) if state.get("wallpaper") else None
    try:
        pal = palette.extract(img)
    except palette.PaletteError as e:
        raise ApplyError(str(e)) from e
    th = derive(pal)
    slot = other(backend.current_slot() or state.get("slot") or "b")
    term_on = bool(state.get("terminal_colors", True))
    term_slot = other(backend.current_term_slot() or state.get("term_slot") or "b")
    ctx = backends.Context(img=img, theme=th, slot=slot, env=env, effect=effect, old=old,
                           terminals=term_on, term_slot=term_slot)
    files, plan = render_all(ctx, backend)
    ctx.icons = plan

    backup.record(files, backend.settings_touched(ctx), reader=backend.read_setting)
    for path, text in files.items():
        write_atomic(path, text)
    if plan:
        write_icons(plan)

    t_set = time.monotonic()
    wait = backend.set_wallpaper(ctx)
    if wait > 0 and effect != "none":
        time.sleep(wait)  # recolour halfway through the transition
    steps = backend.activate(ctx)
    if term_on:
        steps.append(("open terminals", lambda: terminals.send_osc(th)))
    for label, step in steps:
        try:
            step()
        except Exception as e:  # noqa: BLE001 - one step failing never stops the rest
            ctx.notes.append(f"{label}: {e}")
    backend.finish()
    ctx.settle = max(0.0, ctx.settle - (time.monotonic() - t_set))
    update_state(wallpaper=str(img), slot=slot, accent=rgb2hex(th["accent"]), backend=backend.name,
                 **({"term_slot": term_slot} if term_on else {}))
    if not quiet:
        print(f"applied {img.name}: accent {rgb2hex(th['accent'])}, background {rgb2hex(th['bg'])}")
        for note in ctx.notes:
            print(f"  note: {note}")
    write_atomic(paths.cache() / "current.json", _summary(img, th))
    return ctx


def terminals_on(env=None, backend=None):
    """`wallrice terminal on`: from now on terminals follow the wallpaper too, starting with the one on
    show (only the terminals change; the rest of the desktop is already themed)."""
    update_state(terminal_colors=True)
    env = env or detect.detect()
    backend = backend or backends.get(env)
    state = load_state()
    img = Path(state["wallpaper"]) if state.get("wallpaper") else None
    if not img or not img.is_file():
        return []  # nothing applied yet: the next wallpaper brings the colours
    th = derive(palette.extract(img))
    term_slot = other(backend.current_term_slot() or state.get("term_slot") or "b")
    ctx = backends.Context(img=img, theme=th, slot=state.get("slot") or "a", env=env, effect="none",
                           terminals=True, term_slot=term_slot)
    files = terminals.outputs(th, env, term_slot)
    keys = [k for k in backend.settings_touched(ctx) if backend.is_terminal_setting(k)]
    backup.record(files, keys, reader=backend.read_setting)
    for path, text in files.items():
        write_atomic(path, text)
    notes = []
    for label, step in backend.terminal_steps(ctx) + [("open terminals", lambda: terminals.send_osc(th))]:
        try:
            step()
        except Exception as e:  # noqa: BLE001
            notes.append(f"{label}: {e}")
    update_state(term_slot=term_slot)
    return notes


def terminals_off(env=None, backend=None):
    """`wallrice terminal off`: terminals keep their own colours. The terminal's original settings
    come back from the backup, and open terminals are reset to their own colours."""
    update_state(terminal_colors=False)
    env = env or detect.detect()
    backend = backend or backends.get(env)
    restored = backup.restore_where(backend.is_terminal_setting, writer=backend.restore_setting)
    terminals.send_reset()
    return restored


def _summary(img, th):
    """~/.cache/wallrice/current.json: the current colours, for scripts and bars that want them."""
    d = {"wallpaper": str(img), **{k: rgb2hex(th[k]) for k in ("bg", "fg", "accent", "on_accent", "surface",
                                                                "surface2", "muted")}}
    d["term"] = [rgb2hex(c) for c in th["term"]]
    return json.dumps(d, indent=1) + "\n"
