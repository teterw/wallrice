"""Back up before changing anything; `wallrice uninstall` puts it all back.

The manifest records, the first time wallrice is about to change it, each file's original (a copy,
or "absent") and each dconf key's original value (or "unset"). Later changes don't overwrite those
originals. A full `dconf dump /` is kept too, for disaster recovery by hand."""
import json
import shutil
import time
from pathlib import Path

from . import paths
from .render import HEADER
from .sh import has, run
from .state import write_atomic


def manifest_path():
    return paths.backups() / "manifest.json"


def load():
    try:
        m = json.loads(manifest_path().read_text())
    except (OSError, ValueError):
        m = {}
    m.setdefault("files", {})
    m.setdefault("dconf", {})
    return m


def save(m):
    write_atomic(manifest_path(), json.dumps(m, indent=1, sort_keys=True) + "\n")


def ours(path):
    """A file wallrice generated (its header is in the first lines), or a wallrice-only location."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return HEADER in f.read(400)
    except OSError:
        return False


def record(files=(), dconf_keys=(), reader=None):
    """Remember the originals of these files and dconf keys, if not remembered yet."""
    m = load()
    root = paths.backups()
    changed = False
    if not (root / "dconf-full.ini").exists() and has("dconf"):
        rc, out = run("dconf", "dump", "/")
        if rc == 0:
            write_atomic(root / "dconf-full.ini", out, mode=0o600)
            m["created"] = time.strftime("%Y-%m-%d %H:%M:%S")
            changed = True
    for p in map(Path, files):
        key = str(p)
        if key in m["files"] or is_wallrice_path(p):
            continue
        if p.is_file() and not ours(p):
            copy = root / "files" / key.lstrip("/")
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, copy)
            m["files"][key] = str(copy)
        else:
            m["files"][key] = None  # absent (or already ours): uninstall removes it
        changed = True
    for k in dconf_keys:
        if k in m["dconf"]:
            continue
        m["dconf"][k] = (reader or dconf_read)(k)
        changed = True
    if changed:
        save(m)
    return m


def is_wallrice_path(p):
    """Files that only wallrice uses (its own themes, palettes, colour files) need no backup: their
    name, or one of the folders just above, says wallrice."""
    p = Path(p)
    return any("wallrice" in part.lower() for part in (p.name, *p.parent.parts[-3:]))


def dconf_read(key):
    rc, out = run("dconf", "read", key)
    out = out.strip() if rc == 0 else ""
    return out or None


def restore(dry_run=False, say=print, writer=None):
    """Put every recorded original back. `writer(key, value)` restores a setting (the backend's;
    plain dconf by default). Returns the number of things restored."""
    m = load()
    n = 0
    for key, value in sorted(m["dconf"].items()):
        say(f"restore {key} = {value if value is not None else '(unset)'}")
        if not dry_run:
            if writer is not None:
                writer(key, value)
            elif value is None:
                run("dconf", "reset", key)
            else:
                run("dconf", "write", key, value)
        n += 1
    for orig, copy in sorted(m["files"].items()):
        p = Path(orig)
        if copy is None:
            if p.is_file() and ours(p):
                say(f"remove {p}")
                if not dry_run:
                    p.unlink()
                n += 1
        elif Path(copy).is_file():
            say(f"restore {p}")
            if not dry_run:
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(copy, p)
            n += 1
    return n
