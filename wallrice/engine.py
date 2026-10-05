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

from . import backends, backup, detect, palette, parts, paths
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
    if ctx.on("apps"):
        files.update(gtk.outputs(th, slot, extra=backend.gtk_css(ctx)))
        files.update(apps.outputs(th, env))
    if ctx.on("terminal"):
        files.update(terminals.outputs(th, env, ctx.term_slot))
    plan = icons.plan(th["accent"], slot) if ctx.on("icons") else None
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
    on = parts.enabled(state)
    if state.get("paused") or not on["transitions"]:
        effect = "none"
    old = Path(state["wallpaper"]) if state.get("wallpaper") else None
    try:
        pal = palette.extract(img)
    except palette.PaletteError as e:
        raise ApplyError(str(e)) from e
    th = derive(pal)
    slot = other(backend.current_slot() or state.get("slot") or "b")
    term_on = on["terminal"]
    term_slot = other(backend.current_term_slot() or state.get("term_slot") or "b")
    ctx = backends.Context(img=img, theme=th, slot=slot, env=env, effect=effect, old=old,
                           parts=on, term_slot=term_slot)
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


# Files that belong to a part (besides wallrice's own): their originals come back when it's turned off
FILE_PARTS = {"gtk-4.0/gtk.css": "apps", "gtk-3.0/settings.ini": "apps", "gtk-4.0/settings.ini": "apps",
              "lxqt/lxqt.conf": "apps"}


def file_part(path):
    return next((part for tail, part in FILE_PARTS.items() if str(path).endswith(tail)), None)


def part_on(names, env=None, backend=None):
    """`wallrice on PART…`: these parts follow the wallpaper again, starting with the one on show.
    Returns notes about anything that couldn't be done."""
    names = [names] if isinstance(names, str) else list(names)
    st = update_state(**{parts.BY_NAME[n].key: True for n in names})
    notes = []
    if "rotation" in names:
        from . import setup
        setup.set_rotation(st.get("rotate_minutes") or 30, say=lambda *a: None)
    if set(names) - {"rotation", "transitions"}:
        img = Path(st["wallpaper"]) if st.get("wallpaper") else None
        if img and img.is_file():
            ctx = apply(img, effect="none", quiet=True, env=env, backend=backend)
            notes += ctx.notes
    if set(names) & SHELL_PARTS:
        refresh_shell(backend or backends.get(env or detect.detect()), load_state())
    return notes


def part_off(names, env=None, backend=None):
    """`wallrice off PART…`: these parts keep (or get back) their own look. Their original settings come
    back from the backup and are forgotten there, so they're recorded afresh when turned on again.
    Returns how many settings and files were put back."""
    names = [names] if isinstance(names, str) else list(names)
    st = update_state(**{parts.BY_NAME[n].key: False for n in names})
    env = env or detect.detect()
    backend = backend or backends.get(env)
    picked = set(names)
    n = backup.restore_where(lambda k: backend.part_of(k) in picked, writer=backend.restore_setting)
    n += backup.restore_files_where(lambda p: file_part(p) in picked)
    if "terminal" in picked:
        terminals.send_reset()
    if "rotation" in picked:
        from . import setup
        setup.set_rotation(0, say=lambda *a: None)
    if picked & SHELL_PARTS:
        refresh_shell(backend, st)  # the extension puts the stock top bar / dock look back at once
    return n


SHELL_PARTS = {"dock", "taskbar-icons", "topbar"}


def refresh_shell(backend, st):
    """Rewrite the GNOME Shell extension's settings (it restyles live) wherever they're in use."""
    from .backends import gnome
    if backend.name == "gnome" or gnome.shell_css_path().exists():
        gnome.refresh_shell(st)


def terminals_on(env=None, backend=None):
    """`wallrice terminal on`"""
    return part_on("terminal", env, backend)


def terminals_off(env=None, backend=None):
    """`wallrice terminal off`"""
    return part_off("terminal", env, backend)


def _summary(img, th):
    """~/.cache/wallrice/current.json: the current colours, for scripts and bars that want them."""
    d = {"wallpaper": str(img), **{k: rgb2hex(th[k]) for k in ("bg", "fg", "accent", "on_accent", "surface",
                                                                "surface2", "muted")}}
    d["term"] = [rgb2hex(c) for c in th["term"]]
    return json.dumps(d, indent=1) + "\n"
