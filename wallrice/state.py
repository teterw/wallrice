"""state.json (current wallpaper, settings) and review.json (keep / drop choices), written atomically."""
import json
import os
import tempfile
from pathlib import Path

from . import paths

DEFAULTS = {"wallpaper": None, "mode": "all", "paused": False, "animations": True, "rotate_minutes": 30}


def write_atomic(path, text, mode=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_state():
    try:
        d = json.loads(paths.state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {**DEFAULTS, **(d if isinstance(d, dict) else {})}


def save_state(state):
    write_atomic(paths.state_file(), json.dumps(state, indent=1, sort_keys=True) + "\n")


def update_state(**changes):
    s = load_state()
    s.update(changes)
    save_state(s)
    return s


def load_review():
    """Choices from the review and the picker's Delete: paths relative to the walls folder."""
    try:
        d = json.loads(paths.review_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        d = {}
    return {"keep": set(d.get("keep", [])), "drop": set(d.get("drop", []))}


def save_review(review):
    write_atomic(paths.review_file(), json.dumps({k: sorted(review[k]) for k in ("keep", "drop")}, indent=0) + "\n")
